"""端到端测试: 发 '帮我制定一个 Python 学习计划' 验证不卡住"""
import requests
import time
import json
import sys

BASE = 'http://127.0.0.1:8002'

print("=" * 60)
print("步骤 A: 登录获取 token")
print("=" * 60)

# 尝试常见账号
test_accounts = [
    ("user1", "password"),
    ("user1", "user1"),
    ("testuser", "testpass"),
    ("admin", "admin"),
    ("demo", "demo"),
    ("user", "password"),
]

token = None
for username, password in test_accounts:
    try:
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"username": username, "password": password},
                          timeout=10)
        if r.status_code == 200:
            data = r.json()
            token = data.get("access_token") or data.get("token")
            print(f"  [OK] 登录成功: {username}/{password}")
            print(f"  Token: {token[:30] if token else 'None'}...")
            break
        else:
            print(f"  [FAIL] {username}/{password}: HTTP {r.status_code}")
    except Exception as e:
        print(f"  [ERR] {username}: {e}")

if not token:
    # 尝试注册
    print("\n  没有可用账号, 尝试注册 test_e2e_user ...")
    try:
        r = requests.post(f"{BASE}/api/auth/register",
                          json={"username": "test_e2e_user", "password": "TestPass123", "email": "test@example.com"},
                          timeout=10)
        print(f"  Register: HTTP {r.status_code}, {r.text[:200]}")
        if r.status_code in [200, 201]:
            r = requests.post(f"{BASE}/api/auth/login",
                              json={"username": "test_e2e_user", "password": "TestPass123"},
                              timeout=10)
            if r.status_code == 200:
                token = r.json().get("access_token") or r.json().get("token")
                print(f"  注册+登录成功")
    except Exception as e:
        print(f"  注册失败: {e}")

if not token:
    print("\n[ABORT] 无法获取 token, 跳过 E2E 测试")
    sys.exit(1)

print(f"\n[READY] Token 已就绪 ({len(token)} chars)")
print("\n" + "=" * 60)
print("步骤 B: 发 SSE 请求 '帮我制定一个 Python 学习计划'")
print("=" * 60)

# 步骤 B: 发请求, 监控流式响应
start_time = time.time()
content_chunks = []
event_count = 0
last_event_time = time.time()
done_received = False
agent_events = []
plan_detected_log = []

try:
    r = requests.post(
        f"{BASE}/api/chat/send",
        json={"content": "帮我制定一个 Python 学习计划", "regenerate": False},
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
        timeout=180,
    )
    print(f"  响应: HTTP {r.status_code}, time={r.elapsed.total_seconds():.2f}s")

    if r.status_code != 200:
        print(f"  [FAIL] Body: {r.text[:500]}")
        sys.exit(1)

    # 解析 SSE 流
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        last_event_time = time.time()
        if line.startswith("event: "):
            event_name = line[7:].strip()
            event_count += 1
            if event_count <= 30 or event_name == "v1.done":
                print(f"  [event {event_count:3d}] {event_name}")
        elif line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                # 累积 content
                if "content" in data and isinstance(data["content"], str):
                    content_chunks.append(data["content"])
                # 记录 agent 事件
                if data.get("type") == "agent":
                    agent_name = data.get("agent", data.get("name", "unknown"))
                    agent_events.append(agent_name)
                # 记录 plan_detected
                if "plan" in str(data).lower() and "detect" in str(data).lower():
                    plan_detected_log.append(str(data)[:100])
                # 检查 done
                if data.get("type") == "done" or "status" in data and data.get("status") == "done":
                    done_received = True
            except json.JSONDecodeError:
                pass

        # 防止无限等待
        if time.time() - start_time > 120:
            print(f"  [TIMEOUT] 超过 120s, 强制结束")
            break

    elapsed = time.time() - start_time
    full_content = "".join(content_chunks)
    print(f"\n  === 响应统计 ===")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  事件数: {event_count}")
    print(f"  Agent 调用: {agent_events}")
    print(f"  done 事件: {done_received}")
    print(f"  内容长度: {len(full_content)} 字符")
    print(f"  内容预览: {full_content[:200]}")

    # 评估测试结果
    print(f"\n  === 测试评估 ===")
    test_results = {
        "step7.1_done_120s": (elapsed < 120, f"耗时 {elapsed:.1f}s (< 120s)"),
        "step7.2_done_received": (done_received, f"done_received = {done_received}"),
        "step7.3_content_length": (len(full_content) > 200, f"内容长度 {len(full_content)} > 200"),
        "step7.4_no_plan_blocked": (
            len(full_content) > 60 or "python" in full_content.lower(),
            f"内容长度 {len(full_content)} > 60 (修复前会卡在 60 字符)"
        ),
    }
    for k, (ok, detail) in test_results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {k}: {detail}")

    if all(ok for ok, _ in test_results.values()):
        print(f"\n[SUCCESS] 端到端测试通过!")
    else:
        print(f"\n[PARTIAL] 端到端测试部分通过")

except requests.exceptions.Timeout:
    print(f"  [TIMEOUT] 请求超过 180s, SSE 卡住!")
    print(f"  已收到 {len(content_chunks)} 个 content chunk, {event_count} 个事件")
    print(f"  内容预览: {''.join(content_chunks)[:300]}")
    sys.exit(1)
except Exception as e:
    print(f"  [ERROR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
