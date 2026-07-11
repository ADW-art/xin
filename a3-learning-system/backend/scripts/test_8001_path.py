"""决定性测试: 8001 (codex) 是否加载了 P0-B path_agent gate"""
import requests
import time
import json

BASE = 'http://127.0.0.1:8001'

ok_str = "OK"
fail_str = "FAIL"

# 1. 注册并登录
r = requests.post(f'{BASE}/api/auth/register', json={'username': 'old_user_8001_v2', 'password': 'OldUser123', 'email': 'o@e.com'}, timeout=10)
r = requests.post(f'{BASE}/api/auth/login', json={'username': 'old_user_8001_v2', 'password': 'OldUser123'}, timeout=10)
token = r.json().get('access_token')
result = ok_str if token else fail_str
print(f'login: token={result}')

# 2. 发 3 轮"暖机"对话
print('\n=== 暖机 3 轮 ===')
for i, msg in enumerate(['你好', '我有一点 Python 基础, 学过列表和函数', '我想系统学习 Python']):
    r = requests.post(
        f'{BASE}/api/chat/send',
        json={'content': msg},
        headers={'Authorization': f'Bearer {token}'},
        stream=True, timeout=30,
    )
    chunks = []
    for line in r.iter_lines(decode_unicode=True):
        if line.startswith('data: '):
            try:
                d = json.loads(line[6:])
                if 'content' in d and isinstance(d['content'], str):
                    chunks.append(d['content'])
            except:
                pass
    total = len(''.join(chunks))
    print(f'  [{i+1}] {msg[:30]} -> {total} chars')

# 3. 关键测试: path 意图
print('\n=== 关键测试: path 意图 ===')
start = time.time()
content_chunks = []
event_types = []
try:
    r = requests.post(
        f'{BASE}/api/chat/send',
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
                d = json.loads(line[6:])
                if 'content' in d and isinstance(d['content'], str):
                    content_chunks.append(d['content'])
            except:
                pass
        if time.time() - start > 60:
            break
    elapsed = time.time() - start
    content = ''.join(content_chunks)
    et = dict((t, event_types.count(t)) for t in set(event_types))

    print(f'  耗时: {elapsed:.1f}s')
    print(f'  内容: {len(content)} 字符')
    print(f'  事件: {et}')

    has_collab = 'v1.collaboration' in event_types
    has_done = 'v1.done' in event_types
    long_enough = len(content) > 500
    fast = elapsed < 30

    print('\n  === 8001 是否加载 P0-B 修复? ===')
    print(f'  [{"PASS" if has_collab else "FAIL"}] 有 v1.collaboration (path_agent 协同): {et.get("v1.collaboration", 0)} 次')
    print(f'  [{"PASS" if has_done else "FAIL"}] 有 v1.done: {et.get("v1.done", 0)} 次')
    print(f'  [{"PASS" if long_enough else "FAIL"}] 内容 > 500 字符: {len(content)} (修复前 60 字符)')
    print(f'  [{"PASS" if fast else "FAIL"}] 耗时 < 30s: {elapsed:.1f}s (修复前 60s+)')

    if has_collab and has_done and long_enough and fast:
        print('\n  ✅ 8001 加载了我的修复!')
    else:
        print('\n  ❌ 8001 仍是旧 codex 代码, 我的修复未加载')

except Exception as e:
    print(f'  异常: {type(e).__name__}: {e}')
