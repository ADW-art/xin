"""E2E 暖机 + path 意图测试"""
import requests
import time
import json

BASE = 'http://127.0.0.1:8002'

# 登录
r = requests.post(f"{BASE}/api/auth/login", json={"username": "master_e2e_user", "password": "MasterTest123"}, timeout=10)
token = r.json().get("access_token")
print(f"Token: {token[:30]}...")

# 第 1 轮: 暖机 (让 chat_agent 欢迎)
print("\n--- 暖机: 你好 ---")
r = requests.post(
    f"{BASE}/api/chat/send",
    json={"content": "你好"},
    headers={"Authorization": f"Bearer {token}"},
    stream=True, timeout=60,
)
chunks1 = []
for line in r.iter_lines(decode_unicode=True):
    if line.startswith("data: "):
        try:
            data = json.loads(line[6:])
            if "content" in data and isinstance(data["content"], str):
                chunks1.append(data["content"])
        except:
            pass
print(f"  内容: {''.join(chunks1)[:100]}")
print(f"  长度: {len(''.join(chunks1))}")

# 第 2 轮: path 意图 (主测试)
print("\n--- 主测试: 帮我制定一个 Python 学习计划 ---")
start = time.time()
r = requests.post(
    f"{BASE}/api/chat/send",
    json={"content": "帮我制定一个 Python 学习计划"},
    headers={"Authorization": f"Bearer {token}"},
    stream=True, timeout=120,
)
content_chunks = []
event_types = []
for line in r.iter_lines(decode_unicode=True):
    if not line:
        continue
    if line.startswith("event: "):
        event_types.append(line[7:].strip())
    elif line.startswith("data: "):
        try:
            data = json.loads(line[6:])
            if "content" in data and isinstance(data["content"], str):
                content_chunks.append(data["content"])
        except:
            pass
    if time.time() - start > 90:
        break

elapsed = time.time() - start
content = "".join(content_chunks)
event_count = len(event_types)
print(f"  耗时: {elapsed:.1f}s")
print(f"  事件: {event_count}")
print(f"  内容长度: {len(content)} 字符")
print(f"  事件类型: {dict((t, event_types.count(t)) for t in set(event_types))}")
print(f"  内容预览: {content[:300]}")
print()
print(f"  === 关键判定 ===")
print(f"  [{'PASS' if elapsed < 90 else 'FAIL'}] 耗时 < 90s: {elapsed:.1f}s")
print(f"  [{'PASS' if len(content) > 200 else 'FAIL'}] 内容 > 200 字符: {len(content)}")
print(f"  [{'PASS' if 'Python' in content else 'FAIL'}] 含 'Python'")
print(f"  [{'PASS' if '学习' in content else 'FAIL'}] 含 '学习'")
print(f"  [{'PASS' if 'v1.message' in event_types else 'FAIL'}] 有 v1.message")
print(f"  [{'PASS' if 'v1.done' in event_types else 'FAIL'}] 有 v1.done")
