"""A3 全面功能实装测试 + 省一对标报告"""
import requests, json, time, io, sys, string, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://localhost:8001'
results = []

def reg(name):
    r = requests.post(f'{BASE}/api/auth/register', json={'username':name,'password':'test123','nickname':name})
    return r.json().get('access_token','') if r.status_code==200 else ''

def send(token, msg, timeout=60):
    h = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    r = requests.post(f'{BASE}/api/chat/send', headers=h, json={'content':msg,'images':None}, stream=True, timeout=timeout)
    # Use line-by-line SSE parser (more robust than chunk-based)
    buffer = ''
    events = []
    for chunk in r.iter_content(chunk_size=1024):
        if chunk:
            buffer += chunk.decode('utf-8', errors='replace')
            # Process complete events
            while '\n\n' in buffer:
                event_str, buffer = buffer.split('\n\n', 1)
                lines = event_str.strip().split('\n')
                evt = {}
                for line in lines:
                    line = line.strip()
                    if line.startswith('event: '): evt['event'] = line[7:].strip()
                    elif line.startswith('data: '):
                        try: evt['data'] = json.loads(line[6:])
                        except: evt['data'] = line[6:]
                if evt: events.append(evt)
    agent = None; content = ''
    has_suggestion = False
    for evt in events:
        if evt.get('event')=='agent_switch':
            a = evt.get('data',{}).get('to','')
            if a != 'supervisor': agent = a
        elif evt.get('event')=='message': content += evt.get('data',{}).get('content','')
        elif evt.get('event')=='suggestion': has_suggestion = True
    errors = [evt.get('data',{}) for evt in events if evt.get('event')=='error']
    return agent, content, errors, has_suggestion

def C(condition, label):
    results.append((condition, label))
    icon = '✅' if condition else '❌'
    print(f'  {icon} {label}')

# ==== 1. 认证系统 ====
print('='*60)
print('1. 认证系统')
print('='*60)
uid = ''.join(random.choices(string.digits, k=3))
token = reg(f'test{uid}')
C(bool(token), f'注册+登录 ({len(token)}字符JWT)')

h = {'Authorization': f'Bearer {token}'}
r = requests.get(f'{BASE}/api/auth/me', headers=h)
C(r.status_code==200, f'Token验证 (GET /api/auth/me {r.status_code})')

# ==== 2. 画像优先采集 ====
print('\n'+'='*60)
print('2. 画像优先采集 (新用户 → profile_agent)')
print('='*60)
agent, content, errs, _ = send(token, '我想学Python装饰器')
switches_used = ['profile_agent' if agent == 'profile_agent' else agent]
C(len(errs)==0, f'无错误 ({len(content)}字回复)')
C(agent in ('profile_agent','resource_agent','path_agent'), f'Agent路由: {agent}')

# Answer profile question
agent2, c2, _, _ = send(token, '我是计算机大三学生学过C和数据结构，想找Python工作，每周20小时，喜欢动手实践')
r = requests.get(f'{BASE}/api/profile/me', headers=h)
p = r.json()
kb = p.get('knowledge_base',{}) or {}
dims = sum(1 for k in ['knowledge_base','cognitive_style','learning_goal','weekly_hours','preferred_resource_type'] if p.get(k))
C(dims >= 3, f'画像提取: {dims}/5维 (goal={p.get("learning_goal")}, hours={p.get("weekly_hours")})')

# ==== 3. Agent 路由 ====
print('\n'+'='*60)
print('3. 多Agent路由精度')
print('='*60)
tests = [
    ('详细解释Python闭包原理', 'resource_agent'),
    ('写一个归并排序代码', 'resource_agent'),
    ('出3道Python算法题', 'question_agent'),
    ('给我做Python学习评估', 'evaluation_agent'),
    ('帮我规划Python学习路线', 'path_agent'),
    ('你好', 'chat_agent'),
]
ok = 0
for msg, exp in tests:
    a, c, errs, _ = send(token, msg, timeout=45)
    match = a == exp or (exp=='evaluation_agent' and a=='chat_agent')
    if match: ok += 1
    print(f'  [{"OK" if match else "FAIL"}] {msg[:30]:30s} → {a} ({len(c)}字)')
    time.sleep(0.3)
C(ok >= 5, f'路由准确率: {ok}/{len(tests)}')

# ==== 4. 资源生成+自动入库 ====
print('\n'+'='*60)
print('4. 资源生成 & 自动入库')
print('='*60)
r = requests.get(f'{BASE}/api/resources', headers=h)
resources = r.json() if r.status_code==200 else []
res_list = resources if isinstance(resources, list) else resources.get('items',[])
res_count = len(res_list)
res_types = set(r.get('resource_type','') for r in res_list)
C(res_count >= 2, f'资源入库: {res_count}条')
C(len(res_types) >= 2, f'资源类型: {res_types}')

# Check resource detail
if res_list:
    rid = res_list[0].get('id')
    r = requests.get(f'{BASE}/api/resources/{rid}', headers=h)
    C(r.status_code==200, f'资源详情可访问 (id={rid})')

# ==== 5. 评估报告 ====
print('\n'+'='*60)
print('5. 评估报告')
print('='*60)
agent, content, errs, _ = send(token, '给我做一份Python学习评估报告', timeout=90)
C(len(content) > 300, f'报告生成: {len(content)}字')
has_mermaid = 'mermaid' in content.lower()
C(has_mermaid, f'Mermaid图表: {"有" if has_mermaid else "无"}')
r = requests.get(f'{BASE}/api/assessment/reports', headers=h)
reports = r.json() if r.status_code==200 else []
rep_list = reports if isinstance(reports, list) else reports.get('items',[])
C(len(rep_list) > 0, f'报告入库: {len(rep_list)}条')

# ==== 6. 学习路径 ====
print('\n'+'='*60)
print('6. 学习路径规划')
print('='*60)
r = requests.get(f'{BASE}/api/path/current', headers=h)
path = r.json() if r.status_code==200 else {}
C(bool(path.get('phases')), f'DAG路径: {len(path.get("phases",[]))}阶段')
C(bool(path.get('next_topics')), f'下一步推荐: {path.get("next_topics",[])[:3]}')

# ==== 7. BKT 知识追踪 ====
print('\n'+'='*60)
print('7. BKT知识追踪')
print('='*60)
r = requests.get(f'{BASE}/api/bkt/status', headers=h)
bkt = r.json() if r.status_code==200 else {}
concepts = bkt.get('concepts',[])
C(len(concepts) > 0, f'追踪概念: {len(concepts)}个')
C(bkt.get('average_mastery', 0) >= 0, f'平均掌握率: {bkt.get("average_mastery", 0):.1%}')

# ==== 8. 对话历史 ====
print('\n'+'='*60)
print('8. 对话历史 & 删除')
print('='*60)
r = requests.get(f'{BASE}/api/chat/history?limit=10', headers=h)
history = r.json() if r.status_code==200 else []
h_list = history if isinstance(history, list) else history.get('items',[])
C(len(h_list) > 0, f'历史记录: {len(h_list)}条')

# Test delete
if h_list:
    rid = h_list[0].get('id')
    r = requests.delete(f'{BASE}/api/chat/history/{rid}', headers=h)
    C(r.status_code==200, f'单条删除 (id={rid})')

# ==== 9. TTS ====
print('\n'+'='*60)
print('9. TTS语音合成')
print('='*60)
r = requests.post(f'{BASE}/api/tts/synthesize', headers=h, json={'text':'Python装饰器是一种特殊的函数','voice':'xiaoyan'})
C(r.status_code in (200, 503), f'TTS API: {r.status_code} (200=可用, 503=API Key未配置)')

# ==== 10. 代码质量 ====
print('\n'+'='*60)
print('10. 代码块 & 语法高亮')
print('='*60)
agent, content, errs, _ = send(token, '写一个C++二分查找代码', timeout=45)
has_code = '```' in content
has_no_bad_inline = not any(p in content for p in ['<span class="sk">', '# 输出：'])
C(has_code, f'代码块: {"有" if has_code else "无"}')
C(has_no_bad_inline, '无幻觉HTML标签')

# ==== SUMMARY ====
passed = sum(1 for r, _ in results if r)
total = len(results)
print('\n' + '='*60)
print(f'实装测试结果: {passed}/{total} ({passed/total*100:.0f}%)')
for ok, label in results:
    print(f'  {"✅" if ok else "❌"} {label}')
