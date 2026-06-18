"""
Agent 胡言乱语审计脚本
测试 7 个对话场景，捕获路由决策 + 回复内容，分析逻辑问题
"""
import asyncio
import json
import sys
import re
import time
from pathlib import Path

# Fix Windows console encoding for Chinese output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure we can import from backend
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

BASE_URL = "http://127.0.0.1:8001"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMzYiLCJ1c2VybmFtZSI6ImF1ZGl0X3Rlc3RfMDYxNiIsImV4cCI6MTc4MTYzMTc1NSwianRpIjoiZjdlYzZiNWVkOTRjNDAzOTkyNDk0YzA4ZjZiZGY2NTMifQ.gR0U63J1llU4R6AfQYInzpea5xzWbv_lOTT2YGAZVMk"

TEST_CASES = [
    {
        "id": 1,
        "message": "我想学闭包",
        "expected_agent": "resource_agent",
        "checks": ["闭包概念", "资源生成"],
    },
    {
        "id": 2,
        "message": "闭包和装饰器区别是什么",
        "expected_agent": "resource_agent",
        "checks": ["上下文保持", "对比两个概念", "无编造"],
    },
    {
        "id": 3,
        "message": "为什么闭包可以保存状态",
        "expected_agent": "resource_agent",
        "checks": ["深入技术解释", "不自相矛盾"],
    },
    {
        "id": 4,
        "message": "给我一道闭包练习题",
        "expected_agent": "question_agent",
        "checks": ["路由到出题Agent", "题目关于闭包", "有答案和解析"],
    },
    {
        "id": 5,
        "message": "我完全听不懂，请重新解释",
        "expected_agent": "resource_agent",
        "checks": ["识别困惑", "更简单解释", "上下文保持"],
    },
    {
        "id": 6,
        "message": "我已经会了，下一步学什么",
        "expected_agent": "path_agent",
        "checks": ["路由到路径Agent", "推荐合理", "符合知识图谱"],
    },
    {
        "id": 7,
        "message": "我学的是Java，不要讲Python",
        "expected_agent": "resource_agent",
        "checks": ["切换语言", "记住约束"],
    },
]


def parse_sse_stream(text: str) -> list:
    """Parse raw SSE text into structured events"""
    events = []
    current_event = None
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("event: "):
            current_event = {"event": line[7:].strip(), "data": None}
        elif line.startswith("data: "):
            data_str = line[6:]
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                data = data_str
            if current_event:
                current_event["data"] = data
                events.append(current_event)
                current_event = None
    return events


async def send_message(client: httpx.AsyncClient, content: str) -> dict:
    """Send a message to the chat endpoint and parse the SSE response"""
    print(f"\n{'='*80}")
    print(f"[SEND] {content}")
    print(f"{'='*80}")

    start = time.time()
    async with client.stream(
        "POST",
        f"{BASE_URL}/api/chat/send",
        json={"content": content},
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=120.0,
    ) as response:
        raw = ""
        async for chunk in response.aiter_text():
            raw += chunk

    elapsed = time.time() - start

    events = parse_sse_stream(raw)

    # Collect structured info
    result = {
        "message": content,
        "elapsed": round(elapsed, 1),
        "agents_seen": [],
        "agent_switches": [],
        "full_response": "",
        "resource_events": [],
        "error_events": [],
        "progress_events": [],
        "done_status": None,
        "raw_events": events,
    }

    for evt in events:
        etype = evt.get("event", "")
        edata = evt.get("data", {})

        if etype == "agent_switch":
            switch = {"from": edata.get("from"), "to": edata.get("to")}
            result["agent_switches"].append(switch)
            if edata.get("to") not in result["agents_seen"]:
                result["agents_seen"].append(edata.get("to"))
            print(f"  [SWITCH] {edata.get('from')} -> {edata.get('to')}")

        elif etype == "message":
            content_chunk = edata.get("content", "")
            agent = edata.get("agent", "unknown")
            if agent not in result["agents_seen"] and agent:
                result["agents_seen"].append(agent)
            result["full_response"] += content_chunk

        elif etype == "resource":
            result["resource_events"].append(edata)
            print(f"  [RESOURCE] {edata}")

        elif etype == "error":
            result["error_events"].append(edata)
            print(f"  [ERROR] {edata}")

        elif etype == "progress":
            result["progress_events"].append(edata)

        elif etype == "done":
            result["done_status"] = edata

    # Summary
    print(f"  [TIME] {elapsed:.1f}s")
    print(f"  [AGENTS] {result['agents_seen']}")
    print(f"  [SWITCHES] {len(result['agent_switches'])}")
    print(f"  [LENGTH] {len(result['full_response'])} chars")
    if result["resource_events"]:
        print(f"  [RESOURCE] {result['resource_events']}")
    if result["error_events"]:
        print(f"  [ERROR] {result['error_events']}")
    preview = result["full_response"][:200].replace("\n", "\\n")
    print(f"  [PREVIEW] {preview}")

    return result


def analyze_results(results: list):
    """Analyze all test results and report issues"""
    print("\n\n" + "=" * 80)
    print("## Agent Audit Report")
    print("=" * 80)

    issues_p0 = []
    issues_p1 = []
    issues_p2 = []

    for i, (test_case, result) in enumerate(zip(TEST_CASES, results)):
        tid = test_case["id"]
        print(f"\n--- Test {tid}: {test_case['message'][:40]} ---")

        # Check 1: Agent routing
        expected = test_case.get("expected_agent")
        actual_agents = result.get("agents_seen", [])
        actual_agent_str = ", ".join(actual_agents) if actual_agents else "none"

        if expected and expected not in actual_agents:
            issue_desc = f"Routing error (Test {tid}): expected {expected}, got {actual_agent_str}"
            issues_p0.append(issue_desc)
            print(f"  [FAIL] {issue_desc}")
        else:
            print(f"  [OK] Route: {actual_agent_str}")

        # Check 2: Empty response
        full_resp = result.get("full_response", "")
        if not full_resp.strip():
            issue_desc = f"Empty response (Test {tid}): Agent generated nothing"
            issues_p0.append(issue_desc)
            print(f"  [FAIL] {issue_desc}")

        # Check 3: Response relevance
        for check in test_case.get("checks", []):
            print(f"  [CHECK] {check}")

        # Check 4: Content quality heuristics
        common_issues = check_content_quality(full_resp, tid)
        for issue in common_issues:
            if issue["severity"] == "P0":
                issues_p0.append(issue["desc"])
                print(f"  [P0] {issue['desc']}")
            elif issue["severity"] == "P1":
                issues_p1.append(issue["desc"])
                print(f"  [P1] {issue['desc']}")
            else:
                issues_p2.append(issue["desc"])
                print(f"  [P2] {issue['desc']}")

    # Print report
    print("\n\n" + "=" * 80)
    print("## Final Audit Report")
    print("=" * 80)

    print("\n### P0 (Critical)")
    if issues_p0:
        for i, issue in enumerate(issues_p0, 1):
            print(f"  {i}. {issue}")
    else:
        print("  [OK] No P0 issues")

    print("\n### P1 (Medium)")
    if issues_p1:
        for i, issue in enumerate(issues_p1, 1):
            print(f"  {i}. {issue}")
    else:
        print("  [OK] No P1 issues")

    print("\n### P2 (Minor)")
    if issues_p2:
        for i, issue in enumerate(issues_p2, 1):
            print(f"  {i}. {issue}")
    else:
        print("  [OK] No P2 issues")

    return {"P0": issues_p0, "P1": issues_p1, "P2": issues_p2}


def check_content_quality(text: str, test_id: int) -> list:
    """Check content for various quality issues"""
    issues = []

    if not text.strip():
        return [{"severity": "P0", "desc": f"Test {test_id}: Empty response"}]

    text_lower = text.lower()

    # Check for self-contradiction markers
    contradict_patterns = [
        (r"(?:但是|然而|不过|虽然).{0,30}(?:但是|然而|不过).{0,30}(?:不是|没有|不对|错误)", "Possible self-contradiction"),
        (r"(?:一方面).{0,50}(?:另一方面).{0,100}(?:实际上|其实是|不对)", "Logical contradiction in statements"),
    ]
    for pattern, desc in contradict_patterns:
        if re.search(pattern, text):
            issues.append({"severity": "P1", "desc": f"Test {test_id}: {desc}"})

    # Check for repetitive content
    sentences = re.split(r'[。！？\n]', text)
    if len(sentences) > 3:
        for i in range(len(sentences) - 1):
            s1 = sentences[i].strip()
            for j in range(i + 1, min(i + 5, len(sentences))):
                s2 = sentences[j].strip()
                if len(s1) > 15 and len(s2) > 15 and s1 == s2:
                    issues.append({"severity": "P1", "desc": f"Test {test_id}: Repeated identical sentence"})
                    break
            else:
                continue
            break

    # Check for hallucination patterns
    hallucination_markers = [
        (r"根据.*理论(?:研究|表明|显示)", "May have fabricated theoretical references"),
        (r"据统计.{0,20}\d{2,3}%", "May have fabricated statistics"),
        (r"(?:所有|全部|一切).{0,10}(?:都|必定|必然|肯定|一定)", "Overly absolute statements"),
    ]
    for pattern, desc in hallucination_markers:
        if re.search(pattern, text):
            issues.append({"severity": "P1", "desc": f"Test {test_id}: {desc}"})

    # Check response too short for technical question
    context_keywords = ["闭包", "装饰器", "状态", "closure", "decorator"]
    has_keyword = any(kw in text for kw in context_keywords)
    if has_keyword and len(text) < 100:
        issues.append({"severity": "P1", "desc": f"Test {test_id}: Too short ({len(text)} chars), may not fully explain"})

    # Check for irrelevant/off-topic content
    # Test 7 specifically: if user said Java, response should NOT have Python code
    if test_id == 7 and ("python" in text_lower and "java" not in text_lower):
        py_count = text_lower.count("python")
        java_count = text_lower.count("java")
        if py_count > java_count:
            issues.append({"severity": "P0", "desc": f"Test {test_id}: User requested Java but response is Python-heavy"})

    return issues


async def main():
    print("=" * 80)
    print("Agent Audit - Start")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Backend: {BASE_URL}")
    print(f"User: audit_test_0616 (ID: 136)")
    print("=" * 80)

    # Pre-set a basic profile so agents have context
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 0: Set up basic profile
        print("\n[INFO] Setting initial profile...")
        profile_data = {
            "knowledge_base": {"Python基础": 50, "函数": 40},
            "cognitive_style": "visual",
            "learning_goal": "skill",
            "weekly_hours": 10.0,
            "preferred_resource_type": "text",
        }
        try:
            resp = await client.put(
                f"{BASE_URL}/api/profile/me",
                json=profile_data,
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            print(f"  Profile: HTTP {resp.status_code}")
            if resp.status_code == 200:
                print(f"  Profile content: {json.dumps(resp.json(), ensure_ascii=False, indent=2)}")
        except Exception as e:
            print(f"  Profile setup error: {e}")

        results = []
        for test_case in TEST_CASES:
            result = await send_message(client, test_case["message"])
            results.append(result)
            await asyncio.sleep(1)

        # Save full results for reference
        output_file = Path(__file__).parent / "agent_audit_results.json"
        serializable = []
        for r in results:
            item = {k: v for k, v in r.items() if k != "raw_events"}
            item["event_summary"] = [
                {"event": e.get("event"), "data": str(e.get("data"))[:200]}
                for e in r.get("raw_events", [])
            ]
            serializable.append(item)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        print(f"\n[INFO] Detailed results saved: {output_file}")

        # Analyze
        analysis = analyze_results(results)

        # Print full responses for manual review
        print("\n\n" + "=" * 80)
        print("## All Full Responses")
        print("=" * 80)
        for i, r in enumerate(results):
            print(f"\n--- Test {i+1}: {TEST_CASES[i]['message']} ---")
            print(r["full_response"][:2000])
            if len(r["full_response"]) > 2000:
                print(f"\n... (truncated, total {len(r['full_response'])} chars)")

        return analysis


if __name__ == "__main__":
    analysis = asyncio.run(main())

    # Build formal report
    p0 = analysis.get("P0", [])
    p1 = analysis.get("P1", [])
    p2 = analysis.get("P2", [])

    print("\n\n" + "=" * 80)
    print("## 最终审计报告 (Formal Report)")
    print("=" * 80)

    print("\n### P0 (严重问题)")
    if p0:
        for i, issue in enumerate(p0, 1):
            print(f"  {i}. {issue}")
    else:
        print("  无 P0 问题")

    print("\n### P1 (中等问题)")
    if p1:
        for i, issue in enumerate(p1, 1):
            print(f"  {i}. {issue}")
    else:
        print("  无 P1 问题")

    print("\n### P2 (轻微问题)")
    if p2:
        for i, issue in enumerate(p2, 1):
            print(f"  {i}. {issue}")
    else:
        print("  无 P2 问题")
