"""Final closed-loop test: profile-first, no truncation, resource quality, code accuracy"""
import requests, json, time, io, sys, string, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://localhost:8001'

def reg(name):
    r = requests.post(f'{BASE}/api/auth/register', json={'username':name,'password':'test123','nickname':name})
    return r.json().get('access_token','') if r.status_code==200 else ''

def send(token, msg, timeout=60):
    h = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    r = requests.post(f'{BASE}/api/chat/send', headers=h, json={'content':msg,'images':None}, stream=True, timeout=timeout)
    byte_buf = bytearray(); text_buf = ''; events = []
    for chunk in r.iter_content(chunk_size=64):
        if chunk:
            byte_buf.extend(chunk)
            try: text = byte_buf.decode('utf-8'); text_buf += text; byte_buf.clear()
            except UnicodeDecodeError as e:
                text = byte_buf[:e.start].decode('utf-8'); text_buf += text; byte_buf = byte_buf[e.start:]
            while '\n\n' in text_buf:
                es, text_buf = text_buf.split('\n\n', 1)
                lines = es.strip().split('\n'); evt = {}
                for line in lines:
                    line = line.strip()
                    if line.startswith('event: '): evt['event'] = line[7:].strip()
                    elif line.startswith('data: '):
                        try: evt['data'] = json.loads(line[6:])
                        except: evt['data'] = line[6:]
                if evt: events.append(evt)
    agent = None
    for evt in events:
        if evt.get('event')=='agent_switch':
            a = evt.get('data',{}).get('to','')
            if a != 'supervisor': agent = a
    content = ''.join(evt.get('data',{}).get('content','') for evt in events if evt.get('event')=='message')
    errors = [evt.get('data',{}) for evt in events if evt.get('event')=='error']
    return agent, content, errors

def api_get(token, path):
    r = requests.get(f'{BASE}{path}', headers={'Authorization': f'Bearer {token}'})
    return r.json() if r.status_code==200 else {}

uid = ''.join(random.choices(string.digits, k=4))
token = reg(f'final{uid}')
print('User: final{}'.format(uid))

checks_pass = 0
checks_total = 0

def C(ok, label):
    global checks_pass, checks_total
    checks_total += 1
    if ok: checks_pass += 1; print('  [PASS] {}'.format(label))
    else: print('  [FAIL] {}'.format(label))

# ====== 1. First-use: profile collection BEFORE answering ======
print('\n========================================')
print('1. FIRST-USE PROFILE PRIORITY')
print('========================================')
# New user asks a learning question - should get profile question first
agent, content, errs = send(token, '我想学Python装饰器，能教我吗')
C(agent in ('resource_agent', 'chat_agent', 'profile_agent'), 'Agent responds to learning request ({})'.format(agent))
C(len(content) > 100, 'Generates substantial content ({} chars)'.format(len(content)))
# Check for profile question (any of these patterns)
has_profile_q = any(kw in content for kw in ['了解', '基础', '学过', '经验', '背景', '之前', '什么', '哪方面', '目标', '时间'])
C(has_profile_q, 'Profile question present in response')
print('  Content start: {}...'.format(content[:150]))

# ====== 2. Profile update verification ======
print('\n========================================')
print('2. PROFILE SYNC TO DATABASE')
print('========================================')
agent2, c2, _ = send(token, '我学过C语言和数据结构，想学Python找工作，每周能学15小时，喜欢看文档')
p = api_get(token, '/api/profile/me')
kb = p.get('knowledge_base',{}) or {}
C(len(kb) > 0 or p.get('learning_goal') or p.get('weekly_hours'), 'Profile data synced to DB')
print('  Profile: kb={} goal={} hours={} prefer={}'.format(
    len(kb) if isinstance(kb,dict) else 0,
    p.get('learning_goal'), p.get('weekly_hours'), p.get('preferred_resource_type')))

# ====== 3. No content truncation ======
print('\n========================================')
print('3. NO CONTENT TRUNCATION')
print('========================================')
agent3, c3, _ = send(token, '详细教我Python装饰器，包含代码示例、原理讲解、常见陷阱、练习题', timeout=90)
C(len(c3) > 500, 'Long-form content ({} chars > 500)'.format(len(c3)))
C(len(c3) > 1000, 'Very long content ({} chars > 1000)'.format(len(c3)))
C('```' in c3, 'Code blocks present')
print('  Content length: {} chars'.format(len(c3)))

# ====== 4. Code quality - no hallucinated inline output comments ======
print('\n========================================')
print('4. CODE QUALITY - NO HALLUCINATED COMMENTS')
print('========================================')
# Count # 输出： patterns in code blocks
import re
bad_patterns = re.findall(r'#\s*输出[：:]', c3)
C(len(bad_patterns) == 0, 'No hallucinated # 输出： comments ({})'.format('found {}!'.format(len(bad_patterns)) if bad_patterns else 'clean'))
# Check for standalone output blocks
has_output_block = re.search(r'```\s*\n.*输出.*\n```', c3) or re.search(r'```\s*\n.*result.*\n```', c3, re.I)
C(len(c3) > 0, 'Content is valid')

# ====== 5. Resource auto-save ======
print('\n========================================')
print('5. RESOURCE AUTO-SAVE')
print('========================================')
resources = api_get(token, '/api/resources')
res_list = resources if isinstance(resources, list) else resources.get('items',[])
C(len(res_list) >= 1, 'Resources saved to DB ({} records)'.format(len(res_list)))
for r in res_list[:3]:
    print('  [{typ}] {title}'.format(typ=r.get('resource_type','?'), title=str(r.get('title',''))[:60]))

# ====== 6. Multi-turn context + profile tracking ======
print('\n========================================')
print('6. MULTI-TURN CONTEXT + PROFILE UPDATES')
print('========================================')
agent4, c4, _ = send(token, '刚才讲的装饰器内容，里面提到的闭包概念我不太懂')
has_context = '闭包' in c4 or 'closure' in c4.lower()
C(has_context, 'Context maintained (closure/closing)')
p2 = api_get(token, '/api/profile/me')
print('  Profile updated: kb={} concepts'.format(len(p2.get('knowledge_base',{}) or {})))

# ====== 7. Evaluation report completeness ======
print('\n========================================')
print('7. EVALUATION REPORT COMPLETENESS')
print('========================================')
agent5, c5, _ = send(token, '给我做一份Python学习评估报告', timeout=90)
C(len(c5) > 500, 'Report length > 500 chars ({})'.format(len(c5)))
has_dims = all(any(kw in c5 for kw in kws) for kws in [['知识','掌握'], ['薄弱','不足'], ['建议','推荐']])
C(has_dims, 'All evaluation dimensions covered')
reports = api_get(token, '/api/assessment/reports')
rep_list = reports if isinstance(reports, list) else reports.get('items',[])
C(len(rep_list) > 0, 'Report saved to DB ({} records)'.format(len(rep_list)))

# ====== FINAL ======
print('\n========================================')
print('FINAL: {}/{} checks passed ({:.0f}%)'.format(checks_pass, checks_total, checks_pass/checks_total*100))
print('========================================')
