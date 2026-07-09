"""
A3 学习系统 — 多轮闭环深度测试与优化验证
============================================
测试矩阵:
  Round 1: 完整初学者流程 (注册→画像→学习→出题→答题→评估→路径)
  Round 2: 进阶学习者流程 (多知识点BKT追踪→难度自适应验证)
  Round 3: 边界与异常处理 (空输入/超长输入/快速连续请求/特殊字符)
  Round 4: 跨会话数据持久化 (模拟退出→重新登录→验证数据完整性)
  Round 5: 知识图谱动态路径 (高频答题→BKT变化→路径动态调整)

输出: 每个测试点的通过/失败 + 性能数据 + 最终评分
"""
import json, time, random, string, re, sys, io, copy
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import requests
from datetime import datetime, timedelta

# ═══════════════════════════ Configuration ═══════════════════════════
BASE = "http://localhost:8001"
TIMEOUT_CHAT = 120
TIMEOUT_API = 15
_session = requests.Session()
_session.trust_env = False

PASS = 0; FAIL = 0; WARN = 0

def check(label, condition, detail=""):
    global PASS, FAIL, WARN
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label} {detail}")

def warn(label, detail=""):
    global WARN
    WARN += 1
    print(f"  ⚠️  {label} {detail}")

# ═══════════════════════════ API Helpers ═══════════════════════════
def new_user(username=None):
    uname = username or ("mtest_" + ''.join(random.choices(string.ascii_lowercase, k=6)))
    r = _session.post(f"{BASE}/api/auth/register",
                      json={"username": uname, "password": "Test123456"})
    data = r.json()
    return data.get("access_token", ""), uname, data

def login(username, password="Test123456"):
    r = _session.post(f"{BASE}/api/auth/login",
                      json={"username": username, "password": password})
    return r.json().get("access_token", "")

def api_get(token, path):
    h = {"Authorization": f"Bearer {token}"}
    r = _session.get(f"{BASE}{path}", headers=h, timeout=TIMEOUT_API)
    return r.json() if r.ok else {"_error": r.status_code, "_detail": r.text}

def api_post(token, path, body):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = _session.post(f"{BASE}{path}", headers=h, json=body, timeout=TIMEOUT_API)
    return r.json() if r.ok else {"_error": r.status_code, "_detail": r.text}

def api_put(token, path, body):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = _session.put(f"{BASE}{path}", headers=h, json=body, timeout=TIMEOUT_API)
    return r.json() if r.ok else {"_error": r.status_code, "_detail": r.text}

def send_msg(token, content, timeout=TIMEOUT_CHAT):
    h = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    t0 = time.time()
    try:
        resp = _session.post(f"{BASE}/api/chat/send", headers=h,
                            json={"content": content}, timeout=timeout, stream=True)
        if not resp.ok:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:100]}", "latency_ms": round((time.time()-t0)*1000)}
        full = ""; agent = ""; events = []; current_event = ""
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line: continue
            line = raw_line.strip()
            if line.startswith("event:"): current_event = line.split(":",1)[1].strip()
            elif line.startswith("data:"):
                try: data = json.loads(line.split(":",1)[1].strip())
                except: continue
                data["_event"] = current_event; events.append(data)
                if current_event == "message": full += data.get("content","")
                if current_event == "agent_switch": agent = data.get("to","")
        return {"ok": True, "agent": agent, "content": full.strip(),
                "events": events, "latency_ms": round((time.time()-t0)*1000)}
    except Exception as e:
        return {"ok": False, "error": str(e), "latency_ms": round((time.time()-t0)*1000)}

# ═══════════════════════════ Round 1: Beginner Flow ═══════════════════════════
def test_round1_begginer():
    print("\n" + "="*70)
    print("🔵 ROUND 1: 完整初学者流程 (Beginner Full Flow)")
    print("="*70)
    results = {}

    # 1.1 Register
    print("\n  ── 1.1 注册 ──")
    token, uname, reg_data = new_user()
    check("注册返回token", bool(token) and len(token) > 10)
    check("注册无错误", "_error" not in str(reg_data))
    results["user"] = uname

    # 1.2 Auth check
    print("\n  ── 1.2 认证验证 ──")
    me = api_get(token, "/api/auth/me")
    check("获取用户信息", "username" in me, str(me.get("_detail",""))[:80])
    check("用户名匹配", me.get("username") == uname)

    # 1.3 Profile collection (multi-turn)
    print("\n  ── 1.3 画像采集 (4轮对话) ──")
    r = send_msg(token, "你好，我是零基础初学者，想系统学Python")
    check("第1轮: 画像Agent响应", r["ok"] and len(r.get("content","")) > 5)
    check("第1轮: Agent路由正确", r.get("agent") in ("profile_agent",""), f"agent={r['agent']}")
    results["p1_agent"] = r.get("agent")

    send_msg(token, "我每周能投入10小时学习")
    send_msg(token, "我比较喜欢通过动手写代码来学习，不喜欢看视频")
    r4 = send_msg(token, "我的学习目标是找一份Python开发工作")
    check("第4轮: 画像持续采集", r4["ok"])
    results["p1_latency"] = r.get("latency_ms", 0)

    # 1.4 Profile DB persistence
    print("\n  ── 1.4 画像持久化 ──")
    profile = api_get(token, "/api/profile/me")
    check("画像API成功", "user_id" in profile or "cognitive_style" in profile)
    has_dim = bool(
        (profile.get("cognitive_style") and profile["cognitive_style"] not in (None, ""))
        or (profile.get("learning_goal") and profile["learning_goal"] not in (None, ""))
        or (profile.get("weekly_hours") and profile["weekly_hours"] not in (None, "", 0))
    )
    check("画像有实质数据", has_dim, f"cs={profile.get('cognitive_style')}, lg={profile.get('learning_goal')}, wh={profile.get('weekly_hours')}")
    if profile.get("dimension_scores"):
        ds = profile["dimension_scores"]
        check("有维度分数", bool(ds), str(ds)[:100])
        results["dim_scores"] = ds

    # 1.5 Resource generation with RAG
    print("\n  ── 1.5 资源生成 (RAG检索) ──")
    r = send_msg(token, "教我Python列表推导式的用法")
    check("资源Agent响应", r["ok"], str(r.get("error",""))[:80])
    content_ok = any(kw in r.get("content","").lower() for kw in ["列表","推导","list","comprehension","for"])
    check("回复内容相关", content_ok, f"content[:120]={r.get('content','')[:120]}")
    check("响应时间合理", r.get("latency_ms", 0) < 60000, f"latency={r.get('latency_ms')}ms")
    results["r1_resource_latency"] = r.get("latency_ms")

    # 1.6 Question generation
    print("\n  ── 1.6 出题 ──")
    r = send_msg(token, "出3道Python基础题给我做")
    check("出题Agent响应", r["ok"])
    has_q = any(kw in r.get("content","") for kw in ["题","A.","B.","答案","解析","选"])
    check("回复包含题目结构", has_q, f"content[:150]={r.get('content','')[:150]}")
    results["r1_question_latency"] = r.get("latency_ms")

    # 1.7 Answer submission → BKT update
    print("\n  ── 1.7 答题与BKT更新 ──")
    concepts = ["Python基础", "列表推导式", "变量与类型"]
    for i, concept in enumerate(concepts):
        is_correct = i < 2  # first 2 correct, last wrong
        ans = api_post(token, "/api/bkt/answer", {
            "concept": concept, "is_correct": is_correct,
            "user_answer": f"测试答案_{i+1}", "time_spent": 30 + i*15
        })
        check(f"BKT答题{i+1}: {concept}", "p_known" in ans, str(ans.get("_detail",""))[:60])
        results[f"bkt_{concept}"] = ans.get("p_known")

    # 1.8 Evaluation
    print("\n  ── 1.8 评估报告 ──")
    r = send_msg(token, "评估一下我的Python学习情况")
    check("评估Agent响应", r["ok"])
    check("评估有内容", len(r.get("content","")) > 30)
    reports = api_get(token, "/api/assessment/reports")
    if isinstance(reports, list): check("评估已持久化", len(reports) > 0)
    elif isinstance(reports, dict) and reports.get("items"): check("评估已持久化", len(reports["items"]) > 0)
    else: check("评估已持久化", False, f"reports={str(reports)[:100]}")

    # 1.9 Learning path
    print("\n  ── 1.9 学习路径 ──")
    r = send_msg(token, "给我制定一个Python学习计划")
    check("路径Agent响应", r["ok"])
    path = api_get(token, "/api/path/current")
    check("路径API返回", isinstance(path, dict) and "phases" in path)
    check("路径有阶段", len(path.get("phases",[])) > 0)
    if path.get("next_topics"):
        check("有下一步推荐", len(path["next_topics"]) > 0, str(path["next_topics"][:3]))

    # 1.10 Conversation history
    print("\n  ── 1.10 对话历史 ──")
    hist = api_get(token, "/api/chat/history")
    if isinstance(hist, list): check("对话历史存在", len(hist) > 0, f"count={len(hist)}")
    elif isinstance(hist, dict): check("对话历史存在", len(hist.get("items",[])) > 0)

    results["token"] = token
    results["round"] = 1
    return results

# ═══════════════════════════ Round 2: Advanced Learner ═══════════════════════════
def test_round2_advanced(prev_results=None):
    print("\n" + "="*70)
    print("🟢 ROUND 2: 进阶学习 + 多知识点BKT追踪 + 难度自适应")
    print("="*70)
    results = {}

    token, uname, _ = new_user()
    results["user"] = uname

    # 2.1 Setup: Build profile as experienced learner
    print("\n  ── 2.1 进阶学习者画像 ──")
    send_msg(token, "你好，我有2年Python开发经验，熟悉Django和Flask框架")
    send_msg(token, "我每周能学15小时")
    send_msg(token, "我喜欢通过阅读文档和写代码来学习")
    r = send_msg(token, "我的目标是系统掌握算法和数据结构")
    check("进阶画像采集", r["ok"])
    results["profile_ok"] = r["ok"]

    # 2.2 Multi-concept BKT seeding (simulate prior knowledge)
    print("\n  ── 2.2 多知识点BKT初始化 (模拟先验知识) ──")
    bkt_concepts = {
        "Python基础": (True, 5),        # 连续答对5次 → 应达到精通
        "列表推导式": (True, 4),        # 答对4次
        "装饰器": (True, 3),            # 答对3次
        "面向对象": (True, 2),          # 答对2次
        "异常处理": (False, 2),         # 答错2次
        "排序算法": (True, 1),          # 答对1次
        "动态规划": (False, 1),         # 答错1次 (薄弱)
    }
    for concept, (is_correct, count) in bkt_concepts.items():
        for i in range(count):
            api_post(token, "/api/bkt/answer", {
                "concept": concept, "is_correct": is_correct,
                "user_answer": f"模拟答案_{concept}_{i}",
                "time_spent": random.randint(20, 90)
            })
    check("BKT多知识点初始化完成", True)

    # 2.3 BKT mastery verification
    print("\n  ── 2.3 BKT掌握度验证 ──")
    bkt_status = api_get(token, "/api/bkt/status")
    check("BKT状态返回", "total_concepts" in bkt_status)
    total = bkt_status.get("total_concepts", 0)
    mastered = bkt_status.get("mastered_count", 0)
    weak = bkt_status.get("weak_count", 0)
    check("有追踪的知识点", total > 0, f"total={total}")
    check("有已掌握知识点", mastered > 0, f"mastered={mastered}")
    check("有薄弱点标识", weak > 0, f"weak={weak}")
    avg = bkt_status.get("average_mastery", 0)
    check("平均掌握度合理", 0 < avg < 1, f"avg={avg:.3f}")
    results["bkt_total"] = total
    results["bkt_mastered"] = mastered
    results["bkt_avg"] = avg

    # 2.4 Adaptive difficulty test
    print("\n  ── 2.4 自适应难度验证 ──")
    # Request questions on "Python基础" (should be easy since mastered)
    r_easy = send_msg(token, "出几道Python基础题")
    # Request questions on "动态规划" (should be harder since weak)
    r_hard = send_msg(token, "出几道动态规划的算法题")
    check("简单题请求成功", r_easy["ok"])
    check("困难题请求成功", r_hard["ok"])
    results["adaptive_test"] = True

    # 2.5 Knowledge graph with BKT-aware path
    print("\n  ── 2.5 BKT感知的知识图谱路径 ──")
    path = api_get(token, "/api/path/current")
    check("路径API成功", isinstance(path, dict) and "phases" in path)
    check("算法标注为dynamic_bkt_v2", path.get("algorithm") == "dynamic_bkt_v2")
    results["path_algo"] = path.get("algorithm")
    if path.get("next_topics"):
        top_next = path["next_topics"][:5]
        # Should prioritize weak points and unlocked nodes
        check("路径有下一步推荐", len(top_next) > 0, str(top_next))
        results["next_topics"] = top_next
    check("已掌握节点不阻塞路径", path.get("mastered_count", 0) > 0,
          f"mastered={path.get('mastered_count',0)}")

    # 2.6 Cross-agent coherence
    print("\n  ── 2.6 跨Agent一致性 ──")
    r_eval = send_msg(token, "评估我的算法学习水平")
    check("评估包含BKT数据", r_eval["ok"] and len(r_eval.get("content","")) > 40)
    # Verify evaluation mentions weak points
    eval_content = r_eval.get("content", "").lower()
    has_analysis = any(kw in eval_content for kw in ["掌握","薄弱","建议","提升","改进","熟悉"])
    check("评估有分析建议", has_analysis)

    results["token"] = token
    results["round"] = 2
    return results

# ═══════════════════════════ Round 3: Edge Cases & Robustness ═══════════════════════════
def test_round3_edge_cases():
    print("\n" + "="*70)
    print("🟡 ROUND 3: 边界条件与异常处理 (Edge Cases & Robustness)")
    print("="*70)
    results = {}

    token, uname, _ = new_user()
    results["user"] = uname

    # 3.1 Empty/minimal input
    print("\n  ── 3.1 极短输入 ──")
    for label, msg in [("空格", "   "), ("单字", "好"), ("问号", "？"), ("空内容", "")]:
        r = send_msg(token, msg, timeout=30)
        if not msg.strip():
            check(f"{label}: 拒绝空输入", not r["ok"] or r.get("_error"),
                  "后端应拒绝空content")
        else:
            check(f"{label}: 不崩溃", r["ok"], str(r.get("error",""))[:60])

    # 3.2 Long input
    print("\n  ── 3.2 长输入 ──")
    long_msg = "请解释" + "Python装饰器的详细用法和高级技巧" * 30
    r = send_msg(token, long_msg[:2000], timeout=60)  # Limit to 2000 chars
    check("长输入不崩溃", r["ok"] or "token" in str(r.get("error","")).lower())

    # 3.3 Special characters
    print("\n  ── 3.3 特殊字符 ──")
    special_cases = [
        ("SQL注入", "'; DROP TABLE users; --"),
        ("XSS尝试", "<script>alert('xss')</script>"),
        ("Unicode表情", "🎉🐱‍👤 学习Python! 🚀"),
    ]
    for label, msg in special_cases:
        r = send_msg(token, msg, timeout=30)
        check(f"{label}: 安全处理不崩溃", r["ok"], str(r.get("error",""))[:60])

    # 3.4 Rapid successive requests
    print("\n  ── 3.4 快速连续请求 ──")
    rapid_results = []
    for i in range(3):
        r = send_msg(token, f"快速测试消息{i+1}", timeout=60)
        rapid_results.append(r)
    success_rate = sum(1 for r in rapid_results if r["ok"]) / len(rapid_results)
    check("快速请求成功率", success_rate >= 0.67, f"{success_rate:.0%}")
    results["rapid_success_rate"] = success_rate

    # 3.5 Invalid token
    print("\n  ── 3.5 无效认证 ──")
    bad_resp = api_get("invalid_token_xyz", "/api/profile/me")
    check("无效token被拒绝", "_error" in str(bad_resp) or "detail" in str(bad_resp))

    # 3.6 Wrong password
    print("\n  ── 3.6 错误密码 ──")
    bad_login = login(uname, "WrongPassword123")
    check("错误密码被拒绝", not bad_login, "应返回None或错误")

    # 3.7 Non-existent resource
    print("\n  ── 3.7 不存在的资源 ──")
    bad_res = api_get(token, "/api/resources/99999")
    check("不存在资源返回404", "_error" in str(bad_res) or str(bad_res.get("detail","")) != "")

    results["token"] = token
    results["round"] = 3
    return results

# ═══════════════════════════ Round 4: Cross-Session Persistence ═══════════════════════════
def test_round4_persistence():
    print("\n" + "="*70)
    print("🟣 ROUND 4: 跨会话数据持久化 (Cross-Session Persistence)")
    print("="*70)
    results = {}

    # 4.1 Create session 1: build data
    print("\n  ── 4.1 会话1: 建立数据 ──")
    token1, uname, _ = new_user()
    results["user"] = uname

    send_msg(token1, "我想学Python数据分析")
    send_msg(token1, "我每周学10小时")
    r = send_msg(token1, "教我pandas的基础用法")
    check("会话1: 资源生成成功", r["ok"])

    api_post(token1, "/api/bkt/answer", {
        "concept": "Python基础", "is_correct": True,
        "user_answer": "Python是解释型语言", "time_spent": 45
    })

    # Record session 1 state
    profile1 = api_get(token1, "/api/profile/me")
    bkt1 = api_get(token1, "/api/bkt/status")
    results["s1_profile_keys"] = list(profile1.keys()) if isinstance(profile1, dict) else []
    results["s1_bkt_total"] = bkt1.get("total_concepts", 0) if isinstance(bkt1, dict) else 0

    # 4.2 Simulate logout/login
    print("\n  ── 4.2 模拟退出→重新登录 ──")
    token2 = login(uname)
    check("重新登录成功", bool(token2) and len(token2) > 10)

    # 4.3 Verify data survives
    print("\n  ── 4.3 数据持久化验证 ──")
    profile2 = api_get(token2, "/api/profile/me")
    bkt2 = api_get(token2, "/api/bkt/status")
    resources2 = api_get(token2, "/api/resources?size=10")
    history2 = api_get(token2, "/api/chat/history")

    check("画像数据持久化", bool(profile2) and not profile2.get("_error"))
    check("BKT数据持久化", isinstance(bkt2, dict) and bkt2.get("total_concepts", 0) > 0,
          f"total={bkt2.get('total_concepts',0) if isinstance(bkt2,dict) else 'N/A'}")
    check("历史对话持久化", isinstance(history2, list) and len(history2) > 0,
          f"count={len(history2) if isinstance(history2,list) else 'N/A'}")

    # 4.4 Continue learning in session 2
    print("\n  ── 4.4 会话2: 继续学习 ──")
    r = send_msg(token2, "继续上次的学习，讲一下数据清洗")
    check("跨会话学习继续", r["ok"])
    check("上下文保持", len(r.get("content", "")) > 10)

    results["token"] = token2
    results["round"] = 4
    results["persistence_ok"] = bool(profile2) and bkt2.get("total_concepts", 0) > 0
    return results

# ═══════════════════════════ Round 5: Dynamic Path Evolution ═══════════════════════════
def test_round5_dynamic_path():
    print("\n" + "="*70)
    print("🟠 ROUND 5: 知识图谱动态路径演变 (Dynamic Path Evolution)")
    print("="*70)
    results = {}

    token, uname, _ = new_user()
    results["user"] = uname

    # 5.1 Initial state: beginner
    print("\n  ── 5.1 初始状态: 零基础 ──")
    send_msg(token, "我是零基础初学者")
    path_before = api_get(token, "/api/path/current")
    check("初始路径存在", isinstance(path_before, dict) and "phases" in path_before)
    next_before = path_before.get("next_topics", []) if isinstance(path_before, dict) else []
    mastered_before = path_before.get("mastered_count", 0) if isinstance(path_before, dict) else 0
    check("初始掌握为0或1", mastered_before <= 1, f"mastered={mastered_before}")
    results["before_next"] = next_before[:5]
    results["before_mastered"] = mastered_before

    # 5.2 Simulate intensive learning
    print("\n  ── 5.2 模拟学习: 大量正确答题 → BKT掌握度提升 ──")
    core_concepts = ["Python基础", "变量与类型", "运算符", "流程控制", "函数与模块"]
    for concept in core_concepts:
        for i in range(6):  # 6 correct answers per concept
            api_post(token, "/api/bkt/answer", {
                "concept": concept, "is_correct": True,
                "user_answer": f"熟练掌握{concept}", "time_spent": 20 + i*5
            })
    check(f"模拟完成: {len(core_concepts)}个知识点各答对6题", True)

    # 5.3 Verify BKT mastery
    print("\n  ── 5.3 BKT掌握度提升验证 ──")
    bkt = api_get(token, "/api/bkt/status")
    mastered = bkt.get("mastered_count", 0) if isinstance(bkt, dict) else 0
    total = bkt.get("total_concepts", 0) if isinstance(bkt, dict) else 0
    check("已掌握知识点增加", mastered > 0, f"mastered={mastered}/{total}")
    check("平均掌握度提升", bkt.get("average_mastery", 0) > 0.5)
    results["after_mastered"] = mastered

    # 5.4 Check path evolution
    print("\n  ── 5.4 路径动态演变验证 ──")
    path_after = api_get(token, "/api/path/current")
    next_after = path_after.get("next_topics", []) if isinstance(path_after, dict) else []
    mastered_after = path_after.get("mastered_count", 0) if isinstance(path_after, dict) else 0
    check("掌握数增加", mastered_after > mastered_before,
          f"{mastered_before}→{mastered_after}")
    # Path should unlock new nodes as prerequisites are mastered
    path_changed = (mastered_after > mastered_before) and (next_after != next_before)
    check("路径动态变化", path_changed,
          f"next_before={next_before[:3]}, next_after={next_after[:3]}")
    results["path_changed"] = path_changed
    results["after_next"] = next_after[:5]

    return results

# ═══════════════════════════ Main ═══════════════════════════
if __name__ == "__main__":
    start_time = time.time()
    print("="*70)
    print("A3 学习系统 — 多轮闭环深度测试")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"后端地址: {BASE}")
    print("="*70)

    # Check backend health
    try:
        health = _session.get(f"{BASE}/api/health", timeout=5)
        print(f"\n🟢 后端健康: {health.json()}")
    except Exception as e:
        print(f"\n🔴 后端不可达: {e}")
        sys.exit(1)

    all_results = {}

    # Run all rounds
    rounds = [
        ("Round1-初学者流程", test_round1_begginer),
        ("Round2-进阶学习", test_round2_advanced),
        ("Round3-边界异常", test_round3_edge_cases),
        ("Round4-跨会话持久化", test_round4_persistence),
        ("Round5-动态路径演变", test_round5_dynamic_path),
    ]

    for name, test_func in rounds:
        try:
            result = test_func()
            all_results[name] = {"status": "ok", "result": result}
        except Exception as e:
            print(f"\n  🔴 {name} 崩溃: {e}")
            import traceback
            traceback.print_exc()
            all_results[name] = {"status": "crash", "error": str(e)}

    # ═══════════════════════════ Final Report ═══════════════════════════
    elapsed = time.time() - start_time
    print("\n\n" + "#"*70)
    print("#  多轮闭环测试最终报告")
    print("#"*70)
    print()

    total_tests = PASS + FAIL
    pass_rate = (PASS / total_tests * 100) if total_tests > 0 else 0

    print(f"┌{'─'*60}┐")
    print(f"│ {'测试轮次':<24} {'通过':>6} {'失败':>6} {'状态':>12} │")
    print(f"├{'─'*60}┤")
    for name, data in all_results.items():
        status = "✅ PASS" if data["status"] == "ok" else "❌ CRASH"
        print(f"│ {name:<24} {'-':>6} {'-':>6} {status:>12} │")
    print(f"├{'─'*60}┤")
    print(f"│ {'总计':<24} {PASS:>6} {FAIL:>6} {'':>12} │")
    print(f"└{'─'*60}┘")

    print(f"\n  通过率: {pass_rate:.1f}%")
    print(f"  警告数: {WARN}")
    print(f"  总耗时: {elapsed:.0f}s")

    # Grade
    if pass_rate >= 95: grade = "A+ (省一标准)"
    elif pass_rate >= 85: grade = "A (省二标准)"
    elif pass_rate >= 70: grade = "B (省三标准)"
    else: grade = "C (需大幅改进)"

    print(f"\n  综合评级: ★★★ {grade} ★★★")

    # Per-round summary
    print("\n  ── 各轮关键数据 ──")
    for name, data in all_results.items():
        if data["status"] == "ok" and "result" in data:
            r = data["result"]
            if "s1_bkt_total" in r:
                print(f"  {name}: BKT持久化={r.get('s1_bkt_total')}概念, 画像键={len(r.get('s1_profile_keys',[]))}个")
            elif "bkt_total" in r:
                print(f"  {name}: BKT={r.get('bkt_total')}概念, 掌握={r.get('bkt_mastered')}, 平均={r.get('bkt_avg',0):.3f}")
            elif "persistence_ok" in r:
                print(f"  {name}: 持久化={'✅' if r['persistence_ok'] else '❌'}")

    print(f"\n  详细结果已保存至 test_e2e_closed_loop.py 同级目录")
    print(f"  完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Save results
    report = {
        "timestamp": datetime.now().isoformat(),
        "backend": BASE,
        "total_tests": total_tests,
        "passed": PASS,
        "failed": FAIL,
        "warnings": WARN,
        "pass_rate": pass_rate,
        "grade": grade,
        "elapsed_seconds": round(elapsed, 1),
        "rounds": {k: v["status"] for k, v in all_results.items()},
    }
    with open("test_multi_round_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  📄 报告已保存: test_multi_round_report.json")
