"""Master E2E: 完整验证今日所有修复 (含 uvicorn 8002 + SSE 流)"""
import requests
import time
import json
import sys
import os
import tempfile

BASE = 'http://127.0.0.1:8002'

print("=" * 60)
print("Master E2E 测试 - 今日所有修复")
print("=" * 60)

results = []
def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((name, passed, detail))
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")


# 1. Health check
print("\n--- 1. Health Check ---")
try:
    r = requests.get(f"{BASE}/api/health", timeout=10)
    record("E2E.1 Health check", r.status_code == 200, f"HTTP {r.status_code}, body={r.text[:120]}")
except Exception as e:
    record("E2E.1 Health check", False, str(e))
    sys.exit(1)

# 2. Login (register if needed)
print("\n--- 2. Login / Register ---")
username = "master_e2e_user"
password = "MasterTest123"
r = requests.post(f"{BASE}/api/auth/login", json={"username": username, "password": password}, timeout=10)
if r.status_code != 200:
    r = requests.post(f"{BASE}/api/auth/register", json={"username": username, "password": password, "email": "m@e.com"}, timeout=10)
r = requests.post(f"{BASE}/api/auth/login", json={"username": username, "password": password}, timeout=10)
token = r.json().get("access_token") if r.status_code == 200 else None
record("E2E.2 Login", token is not None, f"token={'OK' if token else 'None'}")
if not token:
    sys.exit(1)


# 3. Path 意图 - 验证 Bug #2 (StreamGuard) 修复
print("\n--- 3. Path 意图 (验证 Bug #2 StreamGuard 修复) ---")
def sse_test(user_msg, expected_min_len=200, expected_max_time=60):
    start = time.time()
    content_chunks = []
    event_types = []
    has_done = False
    try:
        r = requests.post(
            f"{BASE}/api/chat/send",
            json={"content": user_msg},
            headers={"Authorization": f"Bearer {token}"},
            stream=True, timeout=180,
        )
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
            if time.time() - start > 120:
                break
        elapsed = time.time() - start
        content = "".join(content_chunks)
        return {
            "elapsed": elapsed,
            "content_len": len(content),
            "event_count": len(event_types),
            "events": dict((t, event_types.count(t)) for t in set(event_types)),
            "content": content,
        }
    except Exception as e:
        return {"error": str(e)}


result_3 = sse_test("帮我制定一个 Python 学习计划", expected_min_len=500, expected_max_time=60)
if "error" in result_3:
    record("E2E.3 Path 意图响应", False, f"异常: {result_3['error']}")
else:
    record("E2E.3.1 响应耗时 < 60s", result_3["elapsed"] < 60, f"{result_3['elapsed']:.1f}s")
    record("E2E.3.2 内容长度 > 500 (修复前卡 60 字符)", result_3["content_len"] > 500, f"{result_3['content_len']} 字符")
    record("E2E.3.3 内容包含 'Python' 和 '学习'", "Python" in result_3["content"] and "学习" in result_3["content"], "OK" if "Python" in result_3["content"] and "学习" in result_3["content"] else "Missing keywords")
    record("E2E.3.4 事件数 > 100", result_3["event_count"] > 100, f"{result_3['event_count']} 事件")
    record("E2E.3.5 有 v1.message 事件", "v1.message" in result_3["events"], f"v1.message={result_3['events'].get('v1.message', 0)}")
    record("E2E.3.6 有 v1.done 事件", "v1.done" in result_3["events"], f"v1.done={result_3['events'].get('v1.done', 0)}")


# 4. Path 路线图 - 短响应验证
print("\n--- 4. Path 路线图 (次要场景) ---")
result_4 = sse_test("Python 学习路线图")
if "error" in result_4:
    record("E2E.4 Path 路线图", False, f"异常: {result_4['error']}")
else:
    record("E2E.4.1 响应 < 30s", result_4["elapsed"] < 30, f"{result_4['elapsed']:.1f}s")
    record("E2E.4.2 内容 > 200 字符", result_4["content_len"] > 200, f"{result_4['content_len']} 字符")
    record("E2E.4.3 有 v1.collaboration (多 agent 协同)", "v1.collaboration" in result_4["events"], f"v1.collaboration={result_4['events'].get('v1.collaboration', 0)}")


# 5. Bug #1: clean_checkpoint_stale_flags 脚本 (不杀 uvicorn, 不破坏对话)
print("\n--- 5. Bug #1: clean_checkpoint_stale_flags 脚本验证 ---")
# 模拟: 先看脚本导入不会执行, 然后命令行调用能跑
import subprocess
r = subprocess.run(
    [sys.executable, "-c", "import scripts.clean_checkpoint_stale_flags as csf; print('IMPORTED_OK', hasattr(csf, 'main'))"],
    cwd=r"E:\code\claude-1\a3-learning-system\backend",
    capture_output=True, text=True, timeout=30,
)
record("E2E.5.1 脚本 import 不执行副作用",
       "IMPORTED_OK True" in r.stdout,
       f"stdout: {r.stdout.strip()[:100]}, stderr: {r.stderr.strip()[:100]}")


# 6. Bug #3: 配置加载验证 (reranker_model/local_path 存在)
print("\n--- 6. Bug #3: 配置加载 ---")
r = subprocess.run(
    [sys.executable, "-c", """
import sys; sys.path.insert(0, r'E:\\\\code\\\\claude-1\\\\a3-learning-system\\\\backend')
from app.config import settings
print('CONFIG_OK', settings.reranker_model, repr(settings.reranker_local_path))
"""],
    cwd=r"E:\code\claude-1\a3-learning-system\backend",
    capture_output=True, text=True, timeout=15,
)
record("E2E.6 reranker 配置加载",
       "CONFIG_OK" in r.stdout and "BAAI/bge-reranker-v2-m3" in r.stdout,
       f"stdout: {r.stdout.strip()[:120]}")


# 7. Bug #4: truncate_messages 智能截断 (实际跑)
print("\n--- 7. Bug #4: truncate_messages 实测 ---")
r = subprocess.run(
    [sys.executable, "-c", """
import sys; sys.path.insert(0, r'E:\\\\code\\\\claude-1\\\\a3-learning-system\\\\backend')
from app.utils.llm_helper import truncate_messages
msgs = [{'role': 'system', 'content': 'sys ' * 100}]
for i in range(11):
    msgs.append({'role': 'user' if i%2==0 else 'assistant', 'content': f'm{i}: ' + 'X' * 20})
msgs.append({'role': 'user', 'content': 'RAG: ' + ('Python 是语言. ' * 200)})
result = truncate_messages(msgs, max_tokens=6000)
print('TRUNCATE_OK', len(msgs), '->', len(result))
"""],
    cwd=r"E:\code\claude-1\a3-learning-system\backend",
    capture_output=True, text=True, timeout=15,
)
record("E2E.7 truncate_messages 13 条不激进截断",
       "TRUNCATE_OK" in r.stdout,
       f"stdout: {r.stdout.strip()[:120]}")

# 同时验证: 13 条不能截到 1 (修复前 bug)
# stdout 格式: "TRUNCATE_OK 13 -> 13"
import re
m = re.search(r"TRUNCATE_OK (\d+) -> (\d+)", r.stdout)
if m:
    before, after = int(m.group(1)), int(m.group(2))
    not_too_aggressive = after >= 5  # 关键: 至少保留 5 条
    record("E2E.7.b 13 条保留 >= 5 (修复前 1)", not_too_aggressive, f"{before} -> {after}")


# 总览
print("\n" + "=" * 60)
print("Master E2E 总览")
print("=" * 60)
total = len(results)
passed = sum(1 for _, p, _ in results if p)
print(f"  通过: {passed}/{total}")
for name, p, detail in results:
    status = "OK" if p else "FAIL"
    print(f"  [{status}] {name}")
