"""
A3 Learning System - End-to-End UX Audit Test Script (v2)
Fixed encoding and tuple unpacking issues.
"""
import requests
import json
import time
import sys
import re
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE = "http://127.0.0.1:8002"
REPORT = []

def ts():
    return time.strftime("%H:%M:%S")

def log(tag, msg):
    line = f"[{ts()}] [{tag}] {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        print(f"[{ts()}] [{tag}] (encoding error, see report)")
    REPORT.append(line)

def sep(title=""):
    line = f"\n{'='*70}\n  {title}\n{'='*70}"
    print(line)
    REPORT.append(line)

# ─── HTTP helpers ────────────────────────────────────────

def check_health():
    return requests.get(f"{BASE}/api/health", timeout=5).json()

def register(username, password, nickname=""):
    r = requests.post(f"{BASE}/api/auth/register", json={
        "username": username, "password": password, "nickname": nickname
    })
    return r.json(), r.status_code

def login(username, password):
    r = requests.post(f"{BASE}/api/auth/login", json={
        "username": username, "password": password
    })
    return r.json(), r.status_code

def get_me(token):
    r = requests.get(f"{BASE}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return r.json(), r.status_code

def get_profile(token):
    r = requests.get(f"{BASE}/api/profile/me", headers={"Authorization": f"Bearer {token}"})
    return r.json(), r.status_code

def get_path(token):
    r = requests.get(f"{BASE}/api/path/current", headers={"Authorization": f"Bearer {token}"})
    return r.json(), r.status_code

def get_bkt_status(token):
    r = requests.get(f"{BASE}/api/bkt/status", headers={"Authorization": f"Bearer {token}"})
    return r.json(), r.status_code

def get_assessment_reports(token):
    r = requests.get(f"{BASE}/api/assessment/reports", headers={"Authorization": f"Bearer {token}"})
    return r.json(), r.status_code

def get_resources(token):
    r = requests.get(f"{BASE}/api/resources", headers={"Authorization": f"Bearer {token}"})
    return r.json(), r.status_code

def get_resource_detail(token, rid):
    r = requests.get(f"{BASE}/api/resources/{rid}", headers={"Authorization": f"Bearer {token}"})
    return r.json(), r.status_code

# ─── SSE chat helper ─────────────────────────────────────

def sse_chat(token, content, timeout=120):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    t0 = time.time()
    resp = requests.post(
        f"{BASE}/api/chat/send",
        json={"content": content},
        headers=headers,
        stream=True,
        timeout=timeout
    )

    events = []
    full_text = ""
    current_agent = "supervisor"
    agent_switches = []
    resources = []
    errors = []

    current_event_type = None
    for raw_line in resp.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("event: "):
            current_event_type = line[7:]
        elif line.startswith("data: ") and current_event_type:
            data_str = line[6:]
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                data = {"raw": data_str}

            events.append({"type": current_event_type, "data": data})

            if current_event_type == "message":
                c = data.get("content", "")
                full_text += c
                current_agent = data.get("agent", current_agent)
            elif current_event_type == "agent_switch":
                agent_switches.append(data)
                current_agent = data.get("to", current_agent)
            elif current_event_type == "resource":
                resources.append(data)
            elif current_event_type == "error":
                errors.append(data)

    elapsed = round(time.time() - t0, 2)

    return {
        "full_text": full_text,
        "agent": current_agent,
        "agent_switches": agent_switches,
        "resources": resources,
        "errors": errors,
        "events": events,
        "elapsed": elapsed,
    }


def quick_quality(text):
    if not text or len(text) < 10:
        return "BAD", "Empty or too short reply"
    if len(text) < 30:
        return "MEDIOCRE", "Reply too short"

    # Hallucination checks
    hallucination_patterns = [
        (r"(?i)delete_all_files", "HALLUCINATION: Mentioned non-existent function"),
        (r"(?i)推荐.*(?:库|package|library|module).*(?:量子|时间旅行|不存在|虚假)", "HALLUCINATION: Recommended fake libraries"),
    ]
    for pattern, desc in hallucination_patterns:
        if re.search(pattern, text):
            return "HALLUCINATION", desc

    # Quality signals
    good_signals = [
        r"```", r"#+ ", r"\*\*", r"Python",
        r"列表推导", r"列表", r"代码", r"示例",
        r"题目", r"正确", r"答案", r"解析",
        r"知识点", r"掌握", r"建议",
    ]
    score = sum(1 for s in good_signals if re.search(s, text))
    if score >= 3:
        return "GOOD", f"Contains structured content (score={score})"
    elif score >= 1:
        return "MEDIOCRE", f"Has some structure (score={score})"
    return "BAD", f"No structure, likely too brief or irrelevant (score={score})"


def test_chat(token, content, label=""):
    sep(f"Chat: {label or content[:50]}...")
    log("INPUT", content)

    result = sse_chat(token, content)
    elapsed = result["elapsed"]

    full = result["full_text"]
    agent = result["agent"]
    truncated = full[:200].replace("\n", " ").replace("\r", " ")

    quality, reason = quick_quality(full)

    log("AGENT", f"Handled by: {agent}")
    log("TIME", f"Response in {elapsed}s")
    log("QUALITY", f"{quality} - {reason}")
    log("REPLY", f"[{len(full)} chars] {truncated}")

    if result["agent_switches"]:
        log("SWITCHES", str(result["agent_switches"]))

    if result["errors"]:
        log("ERRORS", str(result["errors"]))

    if result["resources"]:
        log("RESOURCES", str(result["resources"]))

    return result, quality


# ─── Main Test ───────────────────────────────────────────

def main():
    sep("A3 LEARNING SYSTEM - UX AUDIT")

    try:
        health = check_health()
        log("HEALTH", str(health))
    except Exception as e:
        log("FATAL", f"Backend not responding: {e}")
        return

    uid = str(int(time.time()))[-6:]
    username = f"audit_{uid}"
    password = "test123456"

    # ════════════════════════════════════════════
    # SCENARIO 1: Complete Beginner
    # ════════════════════════════════════════════
    sep("SCENARIO 1: COMPLETE BEGINNER")

    # 1.1 Register
    token_data, status = register(username, password, "TestStudent")
    log("REGISTER", f"Status: {status}")
    log("TOKEN", token_data.get("access_token", "NONE")[:50] + "...")
    token = token_data.get("access_token", "")
    if not token:
        token_data, status = login(username, password)
        log("LOGIN-FALLBACK", f"Status: {status}")
        token = token_data.get("access_token", "")

    me_data, me_status = get_me(token)
    log("AUTH", f"User: {me_data.get('username')} (id={me_data.get('id')})")

    # 1.2 Initial profile
    profile, p_status = get_profile(token)
    log("PROFILE-INIT", f"kb={profile.get('knowledge_base')}, style={profile.get('cognitive_style')}, hours={profile.get('weekly_hours')}")

    # 1.3 Beginner intro
    r1, q1 = test_chat(token, "你好，我是零基础Python初学者，之前没学过编程", "1: Beginner intro")
    time.sleep(1)

    # 1.4 Check profile update
    prof2, _ = get_profile(token)
    log("PROFILE-AFTER1", f"kb={prof2.get('knowledge_base')}, style={prof2.get('cognitive_style')}, hours={prof2.get('weekly_hours')}")

    # 1.5 Weekly hours
    r2, q2 = test_chat(token, "我每周能学8小时", "2: Weekly hours")
    time.sleep(1)

    prof3, _ = get_profile(token)
    log("PROFILE-AFTER2", f"weekly_hours={prof3.get('weekly_hours')} (was {profile.get('weekly_hours')})")

    # 1.6 Learn list comprehension
    r3, q3 = test_chat(token, "教我Python列表推导式", "3: List comprehension")
    time.sleep(1)

    # 1.7 Generate questions
    r4, q4 = test_chat(token, "出3道Python基础题给我做", "4: Generate questions")
    time.sleep(1)

    # 1.8 Submit answers via BKT
    sep("1.8: BKT Answer Submission")
    concepts_found = re.findall(r'知识点[：:]\s*([一-鿿\w]+)', r4["full_text"])
    if not concepts_found:
        concepts_found = ["Python基础", "Python数据类型", "Python运算符"]
    bkt_results = []
    for i, concept in enumerate(concepts_found[:3]):
        try:
            r = requests.post(
                f"{BASE}/api/bkt/answer",
                json={"concept": concept, "is_correct": i % 2 == 0,
                      "user_answer": f"Test answer {i+1}", "time_spent": 60},
                headers={"Authorization": f"Bearer {token}"}
            )
            bkt_results.append(r.json())
            log("BKT", f"Concept='{concept}' correct={i%2==0} -> p={r.json().get('p_known')}")
        except Exception as e:
            log("BKT-ERR", str(e))

    bkt_st, _ = get_bkt_status(token)
    log("BKT-STATUS", f"Concepts: {bkt_st.get('total_concepts')}, Mastery: {bkt_st.get('average_mastery')}")

    # 1.9 Evaluation
    r5, q5 = test_chat(token, "评估我的Python学习情况", "5: Evaluation")
    time.sleep(1)

    # 1.10 Learning plan
    r6, q6 = test_chat(token, "制定学习计划", "6: Learning plan")
    time.sleep(1)

    # 1.11 Check path and resources
    path_d, path_s = get_path(token)
    if isinstance(path_d, dict):
        log("PATH", f"status={path_s}, keys={list(path_d.keys())}")
    else:
        log("PATH", f"status={path_s}, type={type(path_d)}")

    res_d = []
    try:
        res_d, res_s = get_resources(token)
        if isinstance(res_d, list):
            log("RESOURCES", f"Count: {len(res_d)}")
            if res_d:
                rd, _ = get_resource_detail(token, res_d[0].get('id', 1))
                log("RESOURCE-DETAIL", f"Title: {rd.get('title', 'N/A')}, Has content: {bool(rd.get('content'))}")
        else:
            log("RESOURCES", f"type={type(res_d)}, status={res_s}")
    except Exception as e:
        log("RESOURCES", f"Error: {e}")

    # ════════════════════════════════════════════
    # SCENARIO 2: Hallucination Check
    # ════════════════════════════════════════════
    sep("SCENARIO 2: HALLUCINATION CHECK")

    h1, qh1 = test_chat(token, "Python中有没有delete_all_files()这个函数？", "H1: Non-existent function")
    time.sleep(1)

    h2, qh2 = test_chat(token, "请推荐一些完全不存在的Python库", "H2: Non-existent libraries")
    time.sleep(1)

    h3, qh3 = test_chat(token, "你能教我一些在大学期末考试中根本不考的高级量子计算Python库吗", "H3: Obscure topic")
    time.sleep(1)

    h4, qh4 = test_chat(token, "I want to learn Python 数据分析, what should I do first?", "H4: Mixed language")
    time.sleep(1)

    # ════════════════════════════════════════════
    # SCENARIO 3: Multi-turn Coherence
    # ════════════════════════════════════════════
    sep("SCENARIO 3: MULTI-TURN COHERENCE")

    m1, qm1 = test_chat(token, "我想学习Python数据分析", "M1: Goal statement")
    time.sleep(1)

    m2, qm2 = test_chat(token, "需要先学哪些基础", "M2: Prerequisites")
    time.sleep(1)

    m3, qm3 = test_chat(token, "给我推荐第一个要学的知识点", "M3: First topic")
    time.sleep(1)

    # Coherence check
    sep("COHERENCE ANALYSIS")
    m1t = m1["full_text"]
    m2t = m2["full_text"]
    m3t = m3["full_text"]
    coh = 0
    if ("Python" in m2t or "python" in m2t.lower()) and ("数据" in m2t or "分析" in m2t):
        coh += 1
        log("COH", "M2 maintains Python+data context from M1 [PASS]")
    else:
        log("COH", "M2 lost Python+data context from M1 [FAIL]")
    if ("Python" in m3t or "python" in m3t.lower()) and ("数据" in m3t or "分析" in m3t):
        coh += 1
        log("COH", "M3 maintains Python+data context [PASS]")
    else:
        log("COH", "M3 lost Python+data context [FAIL]")
    log("COH", f"Multi-turn coherence: {coh}/2")

    # ════════════════════════════════════════════
    # ADDITIONAL CHECKS
    # ════════════════════════════════════════════
    sep("ADDITIONAL CHECKS")

    # Anonymous user
    anon_r, anon_q = test_chat(None, "什么是Python变量", "Anon: No auth token")
    time.sleep(1)

    # Final state
    final_p, _ = get_profile(token)
    log("FINAL-PROFILE", json.dumps(final_p, ensure_ascii=False))
    final_b, _ = get_bkt_status(token)
    log("FINAL-BKT", f"Concepts: {final_b.get('total_concepts')}, Mastery: {final_b.get('average_mastery')}")
    final_ar, _ = get_assessment_reports(token)
    log("FINAL-REPORTS", f"Reports: {len(final_ar) if isinstance(final_ar, list) else 'N/A'}")

    # ════════════════════════════════════════════
    # SUMMARY
    # ════════════════════════════════════════════
    sep("AUDIT SUMMARY")

    summary = {
        "backend": "http://127.0.0.1:8002",
        "user": username,
        "scenario1": {
            "intro": f"{q1}: {r1['agent']}, {r1['elapsed']}s, {len(r1['full_text'])}chars",
            "hours": f"{q2}: {r2['agent']}, {r2['elapsed']}s, {len(r2['full_text'])}chars",
            "listcomp": f"{q3}: {r3['agent']}, {r3['elapsed']}s, {len(r3['full_text'])}chars",
            "questions": f"{q4}: {r4['agent']}, {r4['elapsed']}s, {len(r4['full_text'])}chars",
            "evaluation": f"{q5}: {r5['agent']}, {r5['elapsed']}s, {len(r5['full_text'])}chars",
            "path": f"{q6}: {r6['agent']}, {r6['elapsed']}s, {len(r6['full_text'])}chars",
        },
        "scenario2": {
            "halluc1": f"{qh1}: {len(h1['full_text'])}chars",
            "halluc2": f"{qh2}: {len(h2['full_text'])}chars",
            "halluc3": f"{qh3}: {len(h3['full_text'])}chars",
            "halluc4": f"{qh4}: {len(h4['full_text'])}chars",
        },
        "scenario3": {
            "m1": f"{qm1}: {len(m1['full_text'])}chars",
            "m2": f"{qm2}: {len(m2['full_text'])}chars",
            "m3": f"{qm3}: {len(m3['full_text'])}chars",
            "coherence": f"{coh}/2",
        },
        "additional": {
            "anonymous_works": anon_q != "BAD" if anon_r['full_text'] else False,
            "profile_updated": prof3.get("weekly_hours") != profile.get("weekly_hours"),
            "bkt_functional": len(bkt_results) > 0,
            "resources_generated": len(res_d) if isinstance(res_d, list) else 0,
        },
    }

    for k, v in summary.items():
        log("SUMMARY", f"{k}: {json.dumps(v, ensure_ascii=False)}")

    # Write report
    import os as _os
    report_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ux_audit_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        for line in REPORT:
            f.write(line + "\n")
        f.write("\n\n=== DETAILED ANALYSIS ===\n\n")

        f.write("## Scenario 1: All Replies\n")
        for i, (r, name) in enumerate([
            (r1, "Beginner intro"), (r2, "Weekly hours"), (r3, "List comprehension"),
            (r4, "Generate questions"), (r5, "Evaluation"), (r6, "Learning plan"),
        ]):
            f.write(f"\n### {name} (Agent: {r['agent']}, {r['elapsed']}s)\n")
            f.write(f"{r['full_text'][:500]}\n")
            if len(r['full_text']) > 500:
                f.write(f"... (truncated, total {len(r['full_text'])} chars)\n")

        f.write("\n## Scenario 2: All Replies\n")
        for r, name in [(h1, "Non-existent function"), (h2, "Fake libraries"), (h3, "Obscure topic"), (h4, "Mixed language")]:
            f.write(f"\n### {name} (Agent: {r['agent']}, {r['elapsed']}s)\n")
            f.write(f"{r['full_text'][:500]}\n")

        f.write("\n## Scenario 3: All Replies\n")
        for r, name in [(m1, "Goal statement"), (m2, "Prerequisites"), (m3, "First topic")]:
            f.write(f"\n### {name} (Agent: {r['agent']}, {r['elapsed']}s)\n")
            f.write(f"{r['full_text'][:500]}\n")

    print(f"\n\n[Report: {report_path}]")
    print("[Total interactions: 13 chat messages]")
    return REPORT


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL: {e}")
        import traceback
        traceback.print_exc()
        # Still write partial report
        try:
            import os as _os3
            report_path2 = _os3.path.join(_os3.path.dirname(_os3.path.abspath(__file__)), "ux_audit_report.txt")
            with open(report_path2, "w", encoding="utf-8") as f:
                for line in REPORT:
                    f.write(line + "\n")
                f.write(f"\n\nFATAL ERROR: {e}\n")
            print(f"Partial report: {report_path2}")
        except Exception:
            pass
