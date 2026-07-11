"""测试 8001 端口 (codex 跑的) 是否加载了我的修复"""
import requests
import time
import json

print("=" * 60)
print(" 8001 端口测试 (codex 跑的)")
print("=" * 60)

# 1. 健康检查
r = requests.get('http://127.0.0.1:8001/api/health', timeout=8)
print(f"\n1. /api/health: HTTP {r.status_code}")
print(f"   body: {r.text[:200]}")

# 2. 登录
r = requests.post('http://127.0.0.1:8001/api/auth/login', json={'username': 'test_8001_user', 'password': 'Test8001'}, timeout=10)
if r.status_code != 200:
    requests.post('http://127.0.0.1:8001/api/auth/register', json={'username': 'test_8001_user', 'password': 'Test8001', 'email': 't@e.com'}, timeout=10)
    r = requests.post('http://127.0.0.1:8001/api/auth/login', json={'username': 'test_8001_user', 'password': 'Test8001'}, timeout=10)
token = r.json().get('access_token')
print(f"\n2. login: HTTP {r.status_code}, token={'OK' if token else 'FAIL'}")

if not token:
    print("\n登录失败, 退出")
    exit(1)

# 3. 关键 E2E
print("\n3. SSE 流测试 (主问题): '帮我制定一个 Python 学习计划'")
start = time.time()
content_chunks = []
event_types = []
try:
    r = requests.post(
        'http://127.0.0.1:8001/api/chat/send',
        json={'content': '帮我制定一个 Python 学习计划'},
        headers={'Authorization': f'Bearer {token}'},
        stream=True, timeout=120,
    )
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith('event: '):
            event_types.append(line[7:].strip())
        elif line.startswith('data: '):
            try:
                data = json.loads(line[6:])
                if 'content' in data and isinstance(data['content'], str):
                    content_chunks.append(data['content'])
            except:
                pass
        if time.time() - start > 60:
            print("   [TIMEOUT 60s]")
            break
    elapsed = time.time() - start
    content = ''.join(content_chunks)
    et = dict((t, event_types.count(t)) for t in set(event_types))

    print(f"\n   耗时: {elapsed:.1f}s")
    print(f"   内容长度: {len(content)} 字符")
    print(f"   事件: {len(event_types)} 个, 类型: {et}")
    print(f"\n   === 关键判定 (修复生效 vs 未生效) ===")
    p1 = elapsed < 30
    p2 = len(content) > 500
    p3 = 'v1.done' in event_types
    print(f"   [{'PASS' if p1 else 'FAIL'}] 耗时 < 30s: {elapsed:.1f}s  (修复前: 卡 60s+)")
    print(f"   [{'PASS' if p2 else 'FAIL'}] 内容 > 500 字符: {len(content)}  (修复前: 卡 60 字符)")
    print(f"   [{'PASS' if p3 else 'FAIL'}] 有 v1.done: {et.get('v1.done', 0)} 次")
    print(f"\n   内容预览: {content[:200]}...")

    if p1 and p2 and p3:
        print("\n   ✅ 8001 端口 (codex 跑的) 也加载了我的修复!")
    else:
        print("\n   ❌ 8001 端口 (codex 跑的) 仍是旧代码, 我的修复没生效")
        print("      原因: codex 的 uvicorn 启动时加载了 commit 09dad00 之前的代码")
        print("      解决: 跟 codex 协调重启 8001")

except Exception as e:
    elapsed = time.time() - start
    print(f"\n   异常: {type(e).__name__}: {e}")
    print(f"   耗时: {elapsed:.1f}s")
    print(f"   累积内容: {len(''.join(content_chunks))} 字符")
    if elapsed >= 30 and len(''.join(content_chunks)) < 100:
        print("\n   ❌ 这就是主人之前遇到的 'StreamGuard 阻断 60 字符' 症状!")
