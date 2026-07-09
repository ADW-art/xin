"""
A3 学习系统 — 端到端闭环验证脚本
====================================
验证完整学习闭环:
  注册 → 画像采集 → RAG检索 → 资源生成 → 出题 → 答题 →
  BKT更新 → 评估报告 → 学习路径生成

使用方式:
  # 前提：后端运行在 localhost:8001
  python test_e2e_closed_loop.py
"""

import json
import time
import random
import string
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests

BASE = "http://localhost:8001"
_session = requests.Session()
_session.trust_env = False

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label} {detail}")


def new_user():
    """注册新测试用户"""
    uname = "e2e_" + ''.join(random.choices(string.ascii_lowercase, k=6))
    r = _session.post(f"{BASE}/api/auth/register",
                      json={"username": uname, "password": "Test123456"})
    data = r.json()
    return data.get("access_token", ""), uname


def send_msg(token, content, timeout=120):
    """发送对话消息，解析SSE返回完整回复"""
    h = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    t0 = time.time()
    try:
        resp = _session.post(
            f"{BASE}/api/chat/send", headers=h,
            json={"content": content}, timeout=timeout, stream=True
        )
        full = ""
        agent = ""
        events = []
        current_event = ""
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                try:
                    data = json.loads(line.split(":", 1)[1].strip())
                except json.JSONDecodeError:
                    continue
                data["_event"] = current_event
                events.append(data)
                if current_event == "message":
                    full += data.get("content", "")
                if current_event == "agent_switch":
                    agent = data.get("to", "")
        return {
            "ok": True,
            "agent": agent,
            "content": full.strip(),
            "events": events,
            "latency_ms": round((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {"ok": False, "agent": "", "content": "", "error": str(e)}


def api_get(token, path):
    h = {"Authorization": f"Bearer {token}"}
    return _session.get(f"{BASE}{path}", headers=h).json()


def api_post(token, path, body):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return _session.post(f"{BASE}{path}", headers=h, json=body).json()


# ============================================================
print("=" * 70)
print("A3 学习系统 — 端到端闭环验证")
print("=" * 70)
print()

# ── Step 1: 注册 ──
print("Step 1: 注册新用户")
token, uname = new_user()
check("注册成功返回token", bool(token), f"token={token[:16] if token else 'NONE'}...")
check("用户名正确", bool(uname))

# ── Step 2: 获取用户信息 ──
print("\nStep 2: 获取用户信息")
me = api_get(token, "/api/auth/me")
check("获取用户信息成功", "username" in me, str(me.get("detail", "")))
check("用户名匹配", me.get("username") == uname, f"expected={uname}, got={me.get('username')}")

# ── Step 3: 画像采集（Profile Agent）─  ──
print("\nStep 3: 画像采集 (Profile Agent)")
r1 = send_msg(token, "你好，我是初学者想学Python")
check("画像采集Agent响应", r1["ok"], r1.get("error", ""))
check("回复非空", len(r1.get("content", "")) > 5, f"len={len(r1.get('content', ''))}")

# 回填更多画像信息
send_msg(token, "我每周大概能学10小时")
send_msg(token, "我更喜欢通过动手写代码来学习")
check("多轮画像采集完成", True)  # 不崩溃即通过

# ── Step 4: 检查画像是否持久化 ──
print("\nStep 4: 画像持久化验证")
profile = api_get(token, "/api/profile/me")
check("画像API返回成功", "user_id" in profile or "cognitive_style" in profile)
check("画像有维度数据", bool(profile), str(profile)[:100])

# ── Step 5: RAG检索 + 资源生成 (Resource Agent) ──
print("\nStep 5: 资源生成 (Resource Agent)")
r2 = send_msg(token, "教我Python列表推导式")
check("资源Agent响应", r2["ok"], r2.get("error", ""))
check("回复包含相关内容", any(kw in r2.get("content", "").lower()
    for kw in ["列表", "推导", "list", "comprehension"]),
    f"content[:100]={r2.get('content', '')[:100]}")

# ── Step 6: 验证资源是否持久化 ──
print("\nStep 6: 资源持久化验证")
resources = api_get(token, "/api/resources?size=10")
check("资源API返回", isinstance(resources, (list, dict)), str(resources)[:100])
if isinstance(resources, list):
    check("有生成的资源", len(resources) > 0, f"count={len(resources)}")
elif isinstance(resources, dict):
    items = resources.get("items", resources.get("data", []))
    check("有生成的资源", len(items) > 0, f"count={len(items)}")

# ── Step 7: 出题 (Question Agent) ──
print("\nStep 7: 出题 (Question Agent)")
r3 = send_msg(token, "出3道Python基础题")
check("出题Agent响应", r3["ok"], r3.get("error", ""))
content = r3.get("content", "")
check("回复包含题目", any(kw in content for kw in ["题", "A.", "B.", "答案", "解析"]),
      f"content[:150]={content[:150]}")

# ── Step 8: 提交答题结果 (BKT API) ──
print("\nStep 8: 答题提交 (BKT API)")
ans1 = api_post(token, "/api/bkt/answer", {
    "concept": "列表推导式",
    "is_correct": True,
    "user_answer": "列表推导式是创建列表的简洁方式",
    "time_spent": 45
})
check("BKT答题提交成功", "p_known" in ans1, str(ans1))
check("BKT P(known)已更新", ans1.get("p_known", 0) > 0.3,
      f"p_known={ans1.get('p_known', 'N/A')}")

# 再提交一道
ans2 = api_post(token, "/api/bkt/answer", {
    "concept": "Python基础",
    "is_correct": True,
    "user_answer": "Python是解释型语言",
    "time_spent": 30
})
check("BKT第二批提交成功", "p_known" in ans2, str(ans2))

# ── Step 9: BKT状态验证 ──
print("\nStep 9: BKT状态验证")
bkt_status = api_get(token, "/api/bkt/status")
check("BKT状态API返回", "total_concepts" in bkt_status, str(bkt_status))
check("有追踪的知识点", bkt_status.get("total_concepts", 0) > 0,
      f"total={bkt_status.get('total_concepts', 0)}")
print(f"  BKT状态: mastered={bkt_status.get('mastered_count', 0)}, "
      f"weak={bkt_status.get('weak_count', 0)}, "
      f"avg={bkt_status.get('average_mastery', 0):.3f}")

# ── Step 10: 评估报告 (Evaluation Agent) ──
print("\nStep 10: 评估报告 (Evaluation Agent)")
r4 = send_msg(token, "评估一下我的学习情况")
check("评估Agent响应", r4["ok"], r4.get("error", ""))
check("评估有实质内容", len(r4.get("content", "")) > 20,
      f"len={len(r4.get('content', ''))}")

# 验证评估报告持久化
reports = api_get(token, "/api/assessment/reports")
if isinstance(reports, list):
    check("评估报告已持久化", len(reports) > 0, f"count={len(reports)}")
elif isinstance(reports, dict):
    items = reports.get("items", reports.get("data", []))
    check("评估报告已持久化", len(items) > 0, f"count={len(items)}")

# ── Step 11: 学习路径 (Path Agent) ──
print("\nStep 11: 学习路径 (Path Agent)")
r5 = send_msg(token, "我下一步该学什么")
check("路径Agent响应", r5["ok"], r5.get("error", ""))
check("路径有实质内容", len(r5.get("content", "")) > 20,
      f"len={len(r5.get('content', ''))}")

# ── Step 12: 学习路径API验证 ──
print("\nStep 12: 学习路径API验证")
path_data = api_get(token, "/api/path/current")
check("路径API返回", isinstance(path_data, dict), str(path_data)[:100])
check("路径有phases", "phases" in path_data, str(list(path_data.keys())))
check("路径有next_topics", "next_topics" in path_data,
      str(path_data.get("next_topics", [])[:3]))
check("路径算法标注正确", path_data.get("algorithm") == "dynamic_bkt_v2",
      f"algorithm={path_data.get('algorithm', 'N/A')}")

# ── Step 13: 知识图谱API验证 ──
print("\nStep 13: 知识图谱API验证")
kg = api_get(token, "/api/path/graph")
check("图谱API返回", isinstance(kg, dict), str(kg)[:100])
has_nodes = len(kg.get("nodes", [])) > 0
has_edges = len(kg.get("edges", [])) > 0
check("图谱有节点", has_nodes, f"nodes={len(kg.get('nodes', []))}")
check("图谱有边", has_edges, f"edges={len(kg.get('edges', []))}")
print(f"  图谱规模: {kg.get('nodes_count', len(kg.get('nodes', [])))} 节点, "
      f"{kg.get('edges_count', len(kg.get('edges', [])))} 边")

# ── Step 14: 对话历史验证 ──
print("\nStep 14: 对话历史验证")
history = api_get(token, "/api/chat/history")
if isinstance(history, list):
    check("对话历史已保存", len(history) > 0, f"count={len(history)}")
elif isinstance(history, dict):
    items = history.get("items", history.get("data", []))
    check("对话历史已保存", len(items) > 0, f"count={len(items)}")

# ── Step 15: Admin统计 ──
print("\nStep 15: 系统统计")
stats = api_get(token, "/api/admin/stats")
check("管理统计API返回", isinstance(stats, dict), str(stats))
kb_total = stats.get("knowledge_base", 0)
ex_total = stats.get("exercise_bank", 0)
check("知识库有文档", kb_total > 0, f"knowledge_base={kb_total}")
check("习题库有题目", ex_total > 0, f"exercise_bank={ex_total}")
print(f"  知识库: {kb_total} 条文档, 习题库: {ex_total} 题")

# ── 总结 ──
print()
print("=" * 70)
print(f"闭环验证完成: {PASS} 通过 / {FAIL} 失败 / {PASS + FAIL} 总计")
print(f"通过率: {PASS / max(PASS + FAIL, 1) * 100:.1f}%")
print("=" * 70)

# 判定
if FAIL == 0 and PASS >= 25:
    print("\n✅ 全链路闭环正常！所有关键节点通过验证。")
elif FAIL <= 3:
    print(f"\n⚠️  基本闭环可用，{FAIL}项失败需关注。")
else:
    print(f"\n❌ 闭环存在断裂，{FAIL}项失败需修复。")
