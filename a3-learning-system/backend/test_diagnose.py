"""快速诊断：Spark API + 各 Agent 独立测试"""
import requests, json, time, random, string

BASE = "http://localhost:8000"

# 注册
uname = "diag_" + ''.join(random.choices(string.ascii_lowercase, k=6))
r = requests.post(f"{BASE}/api/auth/register", json={"username": uname, "password": "Test123456"})
token = r.json().get("access_token", "")
h = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

print("=== 1. 基础连通性 ===")
try:
    r2 = requests.get(f"{BASE}/docs", timeout=5)
    print(f"  Backend: OK ({r2.status_code})")
except Exception as e:
    print(f"  Backend: FAIL - {e}")

print("\n=== 2. 各 Agent 单独测试 (原始SSE) ===")
test_msgs = [
    ("chat", "你好"),
    ("evaluation", "评估一下我的学习情况"),
    ("question", "出3道Python题"),
    ("resource", "教我Python列表"),
    ("path", "下一步学什么"),
    ("profile", "我想学Python"),
]

for label, msg in test_msgs:
    print(f"\n--- [{label}] \"{msg}\" ---")
    try:
        resp = requests.post(f"{BASE}/api/chat/send", headers=h,
                             json={"content": msg}, timeout=60, stream=True)
        event_count = 0
        content_parts = []
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if line.startswith("data:"):
                data_str = line.split(":", 1)[1].strip()
                try:
                    data = json.loads(data_str)
                except:
                    data = {"raw": data_str}
                event_count += 1
                if "content" in data:
                    content_parts.append(data["content"])
                # 打印每个事件的摘要
                keys = list(data.keys())
                preview = str(data)[:120]
                print(f"  event#{event_count} keys={keys} => {preview}")
        full_content = "".join(content_parts)
        print(f"  >> 总事件={event_count} 内容长度={len(full_content)}")
        if full_content:
            print(f"  >> 内容预览: {full_content[:150]}")
        else:
            print(f"  >> 内容为空!")
    except Exception as e:
        print(f"  ERROR: {e}")

print("\n=== 3. 完成 ===")
