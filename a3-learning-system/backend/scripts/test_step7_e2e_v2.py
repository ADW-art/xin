"""E2E 测试 v2: 用更明确的 path 关键词, 验证 path_agent 流程不卡住"""
import requests
import time
import json
import sys

BASE = 'http://127.0.0.1:8002'

# 登录
r = requests.post(f"{BASE}/api/auth/login",
                  json={"username": "test_e2e_user", "password": "TestPass123"},
                  timeout=10)
token = r.json().get("access_token")
print(f"Token: {token[:30]}...")

# 三个典型请求, 测不同意图路径
test_requests = [
    ("帮我制定一个 Python 学习计划", "path 意图 (关键词: 制定, 计划)"),
    ("Python 学习路线图是什么", "path 意图 (关键词: 路线图)"),
    ("讲讲 Python 装饰器", "resource 意图 (关键词: 讲讲)"),
]

for user_msg, desc in test_requests:
    print(f"\n{'='*60}")
    print(f"测试: {desc}")
    print(f"  user: {user_msg}")
    print("=" * 60)

    start = time.time()
    content_chunks = []
    event_types = []
    guard_warnings = []

    try:
        r = requests.post(
            f"{BASE}/api/chat/send",
            json={"content": user_msg},
            headers={"Authorization": f"Bearer {token}"},
            stream=True,
            timeout=180,
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
        full_content = "".join(content_chunks)

        # 关键评估
        is_stuck = elapsed > 60
        is_short = len(full_content) < 50
        truncated_by_guard = is_short and elapsed > 30  # 之前 ~60s

        print(f"  耗时: {elapsed:.1f}s")
        print(f"  事件数: {len(event_types)}")
        print(f"  事件类型: {dict((t, event_types.count(t)) for t in set(event_types))}")
        print(f"  内容长度: {len(full_content)} 字符")
        print(f"  内容预览: {full_content[:200]}")

        # 关键判定
        if truncated_by_guard:
            print(f"  [BUG] 疑似 StreamGuard 截断 (短内容 + 长耗时)")
        elif is_stuck:
            print(f"  [BUG] 卡住 (耗时 > 60s)")
        elif len(full_content) >= 50:
            print(f"  [OK] 正常完成 (内容 >= 50 字符)")
        else:
            print(f"  [INFO] 短响应 (内容 < 50 字符), 可能是 chat 回复")
    except Exception as e:
        print(f"  [ERR] {type(e).__name__}: {e}")
