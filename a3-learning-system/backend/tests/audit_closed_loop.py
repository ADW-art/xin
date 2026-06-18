"""
学习闭环审计 - 验证系统是否为伪闭环
执行所有 5 个验证，对每个给出结论
"""
import urllib.request
import urllib.error
import json
import time
import sys
import random

_ts = str(int(time.time()))[-6:]
_rnd = random.randint(100, 999)

BASE = "http://127.0.0.1:8001"

def req(method, path, token=None, body=None):
    """发送 HTTP 请求"""
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=120)
        return json.loads(resp.read().decode()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode()), e.code

def register(username, password="Test123456", nickname=""):
    data, code = req("POST", "/api/auth/register", body={
        "username": username, "password": password, "nickname": nickname
    })
    if code >= 400:
        print(f"  [FAIL] Register failed ({code}): {data}")
        return None, None
    return data["access_token"], username

def send_chat(token, content, agent_type=None):
    """发送聊天消息（非流式简化版 - 读完整响应）"""
    url = BASE + "/api/chat/send"
    body = {"content": content}
    if agent_type:
        body["agent_type"] = agent_type
    data = json.dumps(body).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    r = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(r, timeout=120)
        raw = resp.read().decode()
        # Parse SSE events
        events = []
        assistant_content = ""
        for line in raw.split("\n"):
            if line.startswith("data: "):
                try:
                    evt = json.loads(line[6:])
                    events.append(evt)
                    if "content" in evt:
                        assistant_content += evt["content"]
                except:
                    pass
        return {"events": events, "assistant_content": assistant_content, "status": 200}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        return {"error": err_body, "status": e.code}

def print_section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def compare_dicts(before, after, label=""):
    """对比两个 dict 的变化"""
    if not before or not after:
        print(f"  {label}: 无法对比（数据为空）")
        return
    changes = []
    all_keys = set(list(before.keys()) + list(after.keys()))
    for k in sorted(all_keys):
        b = before.get(k)
        a = after.get(k)
        if b != a:
            changes.append(f"    {k}: {json.dumps(b, ensure_ascii=False)} → {json.dumps(a, ensure_ascii=False)}")
    if changes:
        print(f"  {label} 变化:")
        for c in changes:
            print(c)
    else:
        print(f"  {label}: 无变化 [FAIL] (伪闭环信号)")


# ================================================================
# 验证 1: "生成资源 = 直接学会?"
# ================================================================
def verify_1():
    print_section("验证1: 生成资源 = 直接学会?")

    print("[1.1] 注册新用户 audit_v1")
    token, _ = register(f"audit_v1_{_ts}_{_rnd}")
    if not token:
        return
    print(f"  Token: {token[:50]}...")

    print("[1.2] 检查初始 BKT 状态")
    bkt_before, _ = req("GET", "/api/bkt/status", token=token)
    print(f"  BKT before: {json.dumps(bkt_before, ensure_ascii=False)}")

    print("[1.3] 检查初始 Profile")
    profile_before, _ = req("GET", "/api/profile/me", token=token)
    print(f"  Profile knowledge_base: {profile_before.get('knowledge_base')}")
    print(f"  Profile dimension_scores: {profile_before.get('dimension_scores')}")

    print("[1.4] 发送「教我Python闭包」→ 资源Agent 生成内容")
    chat_result = send_chat(token, "教我Python闭包")
    if chat_result["status"] >= 400:
        print(f"  [FAIL] Chat failed: {chat_result.get('error')}")
    else:
        content_len = len(chat_result.get("assistant_content", ""))
        print(f"  Assistant 回复长度: {content_len} 字符")
        print(f"  SSE 事件数: {len(chat_result.get('events', []))}")

    print("[1.5] 等待 2 秒后检查 BKT 状态...")
    time.sleep(2)
    bkt_after, _ = req("GET", "/api/bkt/status", token=token)
    print(f"  BKT after: {json.dumps(bkt_after, ensure_ascii=False)}")

    print("[1.6] 检查 Profile knowledge_base 变化")
    profile_after, _ = req("GET", "/api/profile/me", token=token)
    print(f"  Profile knowledge_base: {profile_after.get('knowledge_base')}")
    print(f"  Profile dimension_scores: {profile_after.get('dimension_scores')}")

    # 判断
    print("\n  【判断】")
    if bkt_before.get("total_concepts") == 0 and bkt_after.get("total_concepts") == 0:
        print("  [OK] BKT 正确: 资源生成不等于学会，concepts 仍为 0")
    elif bkt_after.get("total_concepts", 0) > bkt_before.get("total_concepts", 0):
        print("  [FAIL] 伪闭环: 资源生成后 BKT concepts 自动增加（未答题就学会）")

    kb_before = profile_before.get("knowledge_base") or {}
    kb_after = profile_after.get("knowledge_base") or {}
    if kb_before != kb_after:
        print("  [WARN] knowledge_base 变化了（对话触发了 _extract_and_boost）")
        print(f"     这是合理的: knowledge_base 记录学习行为，不等于 BKT mastery")
        print(f"     但需确认 BKT 没有同步提升")
    else:
        print("  [FAIL] knowledge_base 未变化（静默采集未生效）")

    return token

# ================================================================
# 验证 2: "答题正确但 LearningPath 不变?"
# ================================================================
def verify_2():
    print_section("验证2: 答题正确但 LearningPath 不变?")

    print("[2.1] 注册新用户 audit_v2")
    token, _ = register(f"audit_v2_{_ts}_{_rnd}")
    if not token:
        return

    print("[2.2] 建立 Python 画像")
    profile_update, _ = req("PUT", "/api/profile/me", token=token, body={
        "knowledge_base": {"Python基础": 50, "函数": 40, "列表": 30},
        "cognitive_style": "visual",
        "learning_goal": "skill",
        "weekly_hours": 10.0,
        "preferred_resource_type": "text",
    })
    print(f"  画像更新: {json.dumps(profile_update, ensure_ascii=False)[:200]}")

    print("[2.3] 获取初始 LearningPath")
    path_before, _ = req("GET", "/api/path/current", token=token)
    if "detail" in path_before:
        print(f"  Path (初始): {json.dumps(path_before, ensure_ascii=False)[:300]}")
        path_before_data = path_before
    else:
        print(f"  Path (初始): {json.dumps(path_before, ensure_ascii=False)[:300]}")
        path_before_data = path_before

    print("[2.4] 获取初始 BKT 状态")
    bkt_before, _ = req("GET", "/api/bkt/status", token=token)
    print(f"  BKT before: {json.dumps(bkt_before, ensure_ascii=False)[:200]}")

    print("[2.5] BKT 连续答对: Python基础, 函数, 列表")
    answers = [
        {"concept": "Python基础", "is_correct": True},
        {"concept": "函数", "is_correct": True},
        {"concept": "列表", "is_correct": True},
        {"concept": "Python闭包", "is_correct": True},
        {"concept": "装饰器", "is_correct": True},
    ]
    for ans in answers:
        resp, code = req("POST", "/api/bkt/answer", token=token, body={
            "concept": ans["concept"],
            "is_correct": ans["is_correct"]
        })
        print(f"  BKT answer({ans['concept']}, is_correct={ans['is_correct']}): status={code}")
        if code >= 400:
            print(f"    Response: {json.dumps(resp, ensure_ascii=False)[:200]}")

    print("[2.6] 检查 BKT 状态变化")
    bkt_after, _ = req("GET", "/api/bkt/status", token=token)
    print(f"  BKT after: {json.dumps(bkt_after, ensure_ascii=False)}")

    print("[2.7] 检查 LearningPath 变化")
    path_after, _ = req("GET", "/api/path/current", token=token)
    print(f"  Path after: {json.dumps(path_after, ensure_ascii=False)[:300]}")

    # 判断
    print("\n  【判断】")
    before_concepts = bkt_before.get("total_concepts", 0)
    after_concepts = bkt_after.get("total_concepts", 0)
    if after_concepts > before_concepts:
        print(f"  BKT concepts: {before_concepts} → {after_concepts} [OK] BKT 正确更新")
    else:
        print(f"  BKT concepts: {before_concepts} → {after_concepts} [FAIL] BKT 未更新")

    if path_before_data != path_after:
        print("  LearningPath 发生了变化 [OK]")
        compare_dicts(path_before_data, path_after, "Path变化详情")
    else:
        print("  LearningPath 完全不变 [FAIL] 伪闭环: 答题不影响学习路径")

    return token

# ================================================================
# 验证 3: "BKT 变化但 Profile 不变?"
# ================================================================
def verify_3():
    print_section("验证3: BKT变化但Profile不变?")

    print("[3.1] 注册新用户 audit_v3")
    token, _ = register(f"audit_v3_{_ts}_{_rnd}")
    if not token:
        return

    print("[3.2] 更新画像")
    req("PUT", "/api/profile/me", token=token, body={
        "knowledge_base": {"Python基础": 50},
        "cognitive_style": "visual",
        "learning_goal": "skill",
        "weekly_hours": 8.0,
    })

    print("[3.3] 获取初始 Profile 和 BKT")
    profile_before, _ = req("GET", "/api/profile/me", token=token)
    bkt_before, _ = req("GET", "/api/bkt/status", token=token)
    print(f"  Profile knowledge_base: {profile_before.get('knowledge_base')}")
    print(f"  Profile dimension_scores: {profile_before.get('dimension_scores')}")
    print(f"  BKT: {json.dumps(bkt_before, ensure_ascii=False)}")

    print("[3.4] BKT 答对 5 题覆盖 5 个知识点")
    for concept in ["Python基础", "函数", "闭包", "装饰器", "生成器"]:
        req("POST", "/api/bkt/answer", token=token, body={
            "concept": concept, "is_correct": True
        })

    print("[3.5] 检查 BKT 变化")
    bkt_after, _ = req("GET", "/api/bkt/status", token=token)
    print(f"  BKT after: {json.dumps(bkt_after, ensure_ascii=False)}")

    print("[3.6] 检查 Profile 是否同步更新")
    profile_after, _ = req("GET", "/api/profile/me", token=token)
    print(f"  Profile knowledge_base: {profile_after.get('knowledge_base')}")
    print(f"  Profile dimension_scores: {profile_after.get('dimension_scores')}")

    # 判断
    print("\n  【判断】")
    kb_before = profile_before.get("knowledge_base") or {}
    kb_after = profile_after.get("knowledge_base") or {}
    ds_before = profile_before.get("dimension_scores") or {}
    ds_after = profile_after.get("dimension_scores") or {}

    if kb_before != kb_after:
        print("  [OK] Profile knowledge_base 随 BKT 答题同步更新")
    else:
        print("  [FAIL] 伪闭环: BKT 变化但 Profile knowledge_base 未同步")

    if ds_before != ds_after:
        print("  [OK] Profile dimension_scores 随 BKT 答题同步更新")
    else:
        print("  [WARN] dimension_scores 未变化（可能需通过评估Agent生成）")

    return token

# ================================================================
# 验证 4: "Profile 变化但 Dashboard 数据是否同步?"
# ================================================================
def verify_4():
    print_section("验证4: Profile变化 → Dashboard 数据链")

    print("[4.1] 注册新用户 audit_v4")
    token, _ = register(f"audit_v4_{_ts}_{_rnd}")
    if not token:
        return

    print("[4.2] 更新完整画像")
    req("PUT", "/api/profile/me", token=token, body={
        "knowledge_base": {"Python基础": 60, "函数": 50, "数据结构": 40},
        "cognitive_style": "auditory",
        "learning_goal": "exam",
        "weekly_hours": 15.0,
        "preferred_resource_type": "video",
    })

    print("[4.3] 检查各 API 数据一致性")
    profile, _ = req("GET", "/api/profile/me", token=token)
    resources, _ = req("GET", "/api/resources", token=token)
    path, _ = req("GET", "/api/path/current", token=token)
    bkt, _ = req("GET", "/api/bkt/status", token=token)
    assessment_reports, _ = req("GET", "/api/assessment/reports", token=token)

    print(f"  Profile knowledge_base: {profile.get('knowledge_base')}")
    print(f"  Resources count: {resources.get('total', 0) if 'total' in resources else len(resources) if isinstance(resources, list) else 'N/A'}")
    print(f"  Path: {json.dumps(path, ensure_ascii=False)[:150]}")
    print(f"  BKT: {json.dumps(bkt, ensure_ascii=False)[:150]}")
    print(f"  Assessment reports: {json.dumps(assessment_reports, ensure_ascii=False)[:150]}")

    print("[4.4] Dashboard 聚合检查")
    stats, _ = req("GET", "/api/admin/stats", token=token)
    print(f"  Admin stats: {json.dumps(stats, ensure_ascii=False)[:300]}")

    print("\n  【判断】")
    checks = []
    if profile.get("knowledge_base"):
        checks.append("[OK] Profile knowledge_base 可读")
    else:
        checks.append("[FAIL] Profile knowledge_base 为空")
    if "total" in resources or isinstance(resources, list):
        checks.append("[OK] Resources 端点正常")
    else:
        checks.append("[FAIL] Resources 端点异常")
    if not isinstance(bkt, dict):
        checks.append("[FAIL] BKT 端点异常")
    if isinstance(assessment_reports, (list, dict)):
        checks.append("[OK] Assessment reports 端点正常")
        if isinstance(assessment_reports, list):
            checks.append(f"  (共 {len(assessment_reports)} 个报告)")
        if isinstance(assessment_reports, dict) and assessment_reports.get("total", 0) == 0:
            checks.append("  (无报告 - 合理，未生成评估)")
    for c in checks:
        print(f"  {c}")

    return token

# ================================================================
# 验证 5: "跨请求状态一致性（登录/登出/重新登录）"
# ================================================================
def verify_5():
    print_section("验证5: 跨请求状态一致性")

    print("[5.1] 注册新用户 audit_v5")
    username_v5 = f"audit_v5_{_ts}_{_rnd}"
    token, username_v5 = register(username_v5)
    if not token:
        return

    print("[5.2] 建立完整数据")
    # 画像
    req("PUT", "/api/profile/me", token=token, body={
        "knowledge_base": {"Python基础": 70, "闭包": 55, "装饰器": 45},
        "cognitive_style": "reading",
        "learning_goal": "career",
        "weekly_hours": 12.0,
        "preferred_resource_type": "text",
    })
    # BKT 答题
    for concept in ["Python基础", "闭包", "装饰器"]:
        req("POST", "/api/bkt/answer", token=token, body={
            "concept": concept, "is_correct": True
        })
    # 聊天生成资源
    send_chat(token, "教我Python装饰器")

    print("[5.3] 记录登出前数据")
    pre_profile, _ = req("GET", "/api/profile/me", token=token)
    pre_bkt, _ = req("GET", "/api/bkt/status", token=token)
    pre_resources, _ = req("GET", "/api/resources", token=token)
    pre_path, _ = req("GET", "/api/path/current", token=token)
    pre_assess, _ = req("GET", "/api/assessment/reports", token=token)
    pre_reports, _ = req("GET", "/api/assessment/records", token=token)

    print(f"  登出前 Profile: {json.dumps(pre_profile, ensure_ascii=False)[:200]}")
    print(f"  登出前 BKT concepts: {pre_bkt.get('total_concepts')}")
    print(f"  登出前 Resources total: {pre_resources.get('total', 'N/A') if isinstance(pre_resources, dict) else len(pre_resources) if isinstance(pre_resources, list) else 'N/A'}")
    pre_assess_count = len(pre_assess) if isinstance(pre_assess, list) else (pre_assess.get('total', 'N/A') if isinstance(pre_assess, dict) else 'error')
    print(f"  登出前 Assessment reports: {pre_assess_count}")

    print("[5.4] 登出")
    logout_resp, _ = req("POST", "/api/auth/logout", token=token)
    print(f"  Logout: {json.dumps(logout_resp, ensure_ascii=False)}")

    print("[5.5] 尝试用旧 token 请求（应被拒绝）")
    bad_resp, bad_code = req("GET", "/api/profile/me", token=token)
    print(f"  旧 token 访问 profile: {bad_code} {json.dumps(bad_resp, ensure_ascii=False)[:100]}")

    print("[5.6] 重新登录获取新 token")
    login_resp, _ = req("POST", "/api/auth/login", body={
        "username": username_v5, "password": "Test123456"
    })
    new_token = login_resp.get("access_token")
    if not new_token:
        print("  [FAIL] Login failed!")
        return
    print(f"  新 Token: {new_token[:50]}...")

    print("[5.7] 用新 token 重新获取所有数据")
    post_profile, _ = req("GET", "/api/profile/me", token=new_token)
    post_bkt, _ = req("GET", "/api/bkt/status", token=new_token)
    post_resources, _ = req("GET", "/api/resources", token=new_token)
    post_path, _ = req("GET", "/api/path/current", token=new_token)
    post_assess, _ = req("GET", "/api/assessment/reports", token=new_token)
    post_reports, _ = req("GET", "/api/assessment/records", token=new_token)

    print(f"  重新登录后 Profile: {json.dumps(post_profile, ensure_ascii=False)[:200]}")
    print(f"  重新登录后 BKT concepts: {post_bkt.get('total_concepts')}")
    print(f"  重新登录后 Resources total: {post_resources.get('total', 'N/A') if isinstance(post_resources, dict) else len(post_resources) if isinstance(post_resources, list) else 'N/A'}")
    post_assess_count = len(post_assess) if isinstance(post_assess, list) else (post_assess.get('total', 'N/A') if isinstance(post_assess, dict) else 'error')
    print(f"  重新登录后 Assessment reports: {post_assess_count}")

    # 判断
    print("\n  【判断】")
    issues = []

    if bad_code == 401:
        issues.append("[OK] 旧 token 已被拒绝（登出生效）")
    else:
        issues.append(f"[FAIL] 旧 token 仍可用 (code={bad_code})")

    if pre_profile.get("knowledge_base") == post_profile.get("knowledge_base"):
        issues.append("[OK] Profile knowledge_base 跨会话一致")
    else:
        issues.append("[FAIL] Profile knowledge_base 跨会话丢失")

    pre_concepts = pre_bkt.get("total_concepts", 0)
    post_concepts = post_bkt.get("total_concepts", 0)
    if pre_concepts == post_concepts:
        issues.append(f"[OK] BKT concepts 跨会话一致 ({pre_concepts})")
    else:
        issues.append(f"[FAIL] BKT concepts 跨会话丢失: {pre_concepts} → {post_concepts}")

    pre_total = pre_resources.get("total") if isinstance(pre_resources, dict) else (len(pre_resources) if isinstance(pre_resources, list) else "?")
    post_total = post_resources.get("total") if isinstance(post_resources, dict) else (len(post_resources) if isinstance(post_resources, list) else "?")
    if pre_total == post_total:
        issues.append(f"[OK] Resources 跨会话一致 ({pre_total})")
    else:
        issues.append(f"[FAIL] Resources 跨会话丢失: {pre_total} → {post_total}")

    for i in issues:
        print(f"  {i}")

    return new_token

# ================================================================
# 主流程
# ================================================================
if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         A3 学习系统 - 闭环审计工具                          ║")
    print("║         验证对象: http://127.0.0.1:8001                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    results = {}

    # 检查服务状态
    try:
        health, _ = req("GET", "/api/health")
        print(f"\n[OK] 后端服务运行中: {json.dumps(health, ensure_ascii=False)}")
    except Exception as e:
        print(f"\n[FAIL] 后端服务不可达: {e}")
        sys.exit(1)

    verify_1()
    print("\n" + "-"*70)
    verify_2()
    print("\n" + "-"*70)
    verify_3()
    print("\n" + "-"*70)
    verify_4()
    print("\n" + "-"*70)
    verify_5()

    print("\n\n")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                    审计完成                                  ║")
    print("╚══════════════════════════════════════════════════════════════╝")
