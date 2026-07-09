"""T2 意图分类诊断脚本"""
import requests, random, string, json, time

s = requests.Session()
s.trust_env = False
BASE = 'http://localhost:8001'

uname = 't2diag_' + ''.join(random.choices(string.ascii_lowercase, k=8))
r = s.post(f'{BASE}/api/auth/register', json={'username': uname, 'password': 'Test123456'})
token = r.json().get('access_token', '')
h = {'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}

cases = [
    ('你好', 'chat'), ('今天天气怎么样', 'chat'), ('你叫什么名字', 'chat'),
    ('评估一下我的学习情况', 'evaluation'), ('看看我最近学得怎么样', 'evaluation'), ('生成一份学习报告', 'evaluation'),
    ('出几道Python算法题', 'question'), ('给我出5道数据结构的题', 'question'), ('我想刷一些算法题', 'question'),
    ('教我一下Python装饰器', 'resource'), ('解释一下什么是递归', 'resource'), ('帮我学一下快速排序', 'resource'),
    ('我下一步该学什么', 'path'), ('Python学到哪了，接下来呢', 'path'), ('给我制定一个学习计划', 'path'),
    ('我是初学者，想学Python', 'profile'), ('我有一定编程基础', 'profile'), ('我的目标是找一份Python开发工作', 'profile'),
]

ok = 0
fail_detail = []
for msg, expected in cases:
    try:
        resp = s.post(f'{BASE}/api/chat/send', headers=h, json={'content': msg}, timeout=60, stream=True)
        agent = ''
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                text = line.decode('utf-8')
            except Exception:
                text = line.decode('latin-1')
            if text.startswith('data: '):
                try:
                    d = json.loads(text[6:])
                    if 'agent' in d:
                        agent = d['agent']
                except Exception:
                    pass

        if expected == 'chat' and agent in ('supervisor', ''):
            correct = True
        elif expected != 'chat' and agent == f'{expected}_agent':
            correct = True
        else:
            correct = False

        if correct:
            ok += 1
        else:
            fail_detail.append((msg, expected, agent))
        status = 'OK' if correct else 'FAIL'
        print(f'  [{status}] {msg:30s} -> agent={agent:25s} expect={expected}')
        time.sleep(0.3)
    except Exception as e:
        fail_detail.append((msg, expected, f'ERROR:{e}'))
        print(f'  [ERR] {msg:30s} -> {e}')

print(f'\n>>> T2: {ok}/{len(cases)} = {ok / len(cases) * 100:.1f}%')
if fail_detail:
    print('\n--- FAIL DETAIL ---')
    for m, exp, got in fail_detail:
        print(f'  "{m}" expect={exp} got={got}')
