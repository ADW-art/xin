"""单独测试每个 Agent 的完整 SSE 流"""
import requests, json, random, string

BASE = "http://localhost:8001"
_s = requests.Session()
_s.trust_env = False
uname = "agent_" + ''.join(random.choices(string.ascii_lowercase, k=6))
r = _s.post(f"{BASE}/api/auth/register", json={"username": uname, "password": "Test123456"})
token = r.json()["access_token"]
h = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

agents = [
    ("evaluation", "评估一下我的学习情况"),
    ("path", "我下一步该学什么"),
    ("question", "出3道Python基础题"),
    ("resource", "教我Python列表推导式"),
    ("profile", "我是初学者想学Python"),
]

for label, msg in agents:
    print(f"\n{'='*60}")
    print(f"[{label}] \"{msg}\"")
    print(f"{'='*60}")
    try:
        resp = _s.post(f"{BASE}/api/chat/send", headers=h,
                             json={"content": msg}, timeout=90, stream=True)
        events = []
        content_parts = []
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if line.startswith("event:"):
                continue
            if line.startswith("data:"):
                data_str = line.split(":", 1)[1].strip()
                try:
                    data = json.loads(data_str)
                except:
                    data = {"raw": data_str}
                events.append(data)
                if "content" in data:
                    content_parts.append(data["content"])
                # 打印每个非 message 事件
                if "content" not in data:
                    print(f"  EVENT: {data}")

        full = "".join(content_parts)
        print(f"\n  >> 总事件: {len(events)}")
        print(f"  >> message事件: {len(content_parts)}")
        print(f"  >> 总内容长度: {len(full)}")
        if full:
            print(f"  >> 前200字符: {full[:200]}")
            # 检查编码
            try:
                full.encode('utf-8')
                print(f"  >> 编码: UTF-8 OK")
            except:
                print(f"  >> 编码: 有问题!")
        else:
            print(f"  >> 内容为空!!!")
    except Exception as e:
        print(f"  ERROR: {e}")
