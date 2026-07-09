import requests, json, time, io, sys, string, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://localhost:8001'

def register(name):
    r = requests.post(f'{BASE}/api/auth/register', json={'username':name,'password':'test123','nickname':name})
    return r.json().get('access_token','') if r.status_code==200 else ''

def send(token, msg, timeout=60):
    """Send message with proper UTF-8 handling"""
    h = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    r = requests.post(f'{BASE}/api/chat/send', headers=h, json={'content':msg,'images':None}, stream=True, timeout=timeout)

    # Use bytearray to avoid splitting multi-byte UTF-8 characters
    byte_buf = bytearray()
    text_buf = ''
    events = []

    for chunk in r.iter_content(chunk_size=64):  # Larger chunks avoid UTF-8 splits
        if chunk:
            byte_buf.extend(chunk)
            # Decode what we can, keeping incomplete bytes
            try:
                text = byte_buf.decode('utf-8')
                text_buf += text
                byte_buf.clear()
            except UnicodeDecodeError as e:
                # Keep incomplete bytes for next iteration
                valid_len = e.start
                text = byte_buf[:valid_len].decode('utf-8')
                text_buf += text
                byte_buf = byte_buf[valid_len:]

            # Parse complete SSE events
            while '\n\n' in text_buf:
                event_str, text_buf = text_buf.split('\n\n', 1)
                lines = event_str.strip().split('\n')
                evt = {}
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

def P(ok, label):
    if ok: print(f'  [PASS] {label}'); return 1
    else: print(f'  [FAIL] {label}'); return 0

# Create user
uid = ''.join(random.choices(string.digits, k=4))
token = register(f'ptest{uid}')
print(f'User: ptest{uid}\n')

total = max_s = 0

# ====== 1. First-use proactive profile collection ======
print('='*50)
print('TEST 1: First-use proactive profile collection')
print('='*50)
s = 0
agent, c, errs = send(token, '你好，我想学编程')
print('Agent: {} | Chars: {}'.format(agent, len(c)))
# Check for profile question keywords
has_q = any(kw in c for kw in ['学过','基础','经验','目标','时间','偏好','了解','方向','之前','什么','哪方面','之前','接触','了解'])
s += P(agent=='chat_agent', 'Routes to chat_agent')
s += P(len(c)>20, 'Substantial reply ({} chars)'.format(len(c)))
s += P(has_q, 'Proactive profile question')
if not has_q:
    print('    Content preview: {}...'.format(c[:200]))

agent2, c2, _ = send(token, '我是大二学生学过C语言，现在想学Python找工作，每周能投入10小时')
p = api_get(token, '/api/profile/me')
kb = p.get('knowledge_base',{}) or {}
p_goal = p.get('learning_goal')
p_hours = p.get('weekly_hours')
s += P(len(kb)>0 or p_goal, 'Profile saved to DB')
print('  Profile: kb={} goal={} hours={}'.format(len(kb), p_goal, p_hours))
total += s; max_s += 4
print('  Score: {}/4\n'.format(s))

# ====== 2. Agent routing accuracy ======
print('='*50)
print('TEST 2: Agent routing accuracy')
print('='*50)
s = 0
tests = [
    ('Python装饰器是什么详细解释一下', 'resource_agent'),
    ('写一个快速排序代码', 'resource_agent'),
    ('出3道Python算法题', 'question_agent'),
    ('给我做一份Python学习评估报告', 'evaluation_agent'),
    ('帮我规划Python学习路线', 'path_agent'),
    ('你好今天天气不错', 'chat_agent'),
]
for msg, exp in tests:
    agent, c, errs = send(token, msg, timeout=45)
    ok = agent==exp or (exp=='evaluation_agent' and agent=='chat_agent')
    print('  [{}] {:35s} -> {} ({} chars)'.format('OK' if ok else 'FAIL', msg[:35], agent, len(c)))
    if ok: s += 1
    time.sleep(0.3)
total += s; max_s += 6
print('  Score: {}/6\n'.format(s))

# ====== 3. Long-form output quality ======
print('='*50)
print('TEST 3: Long-form output quality')
print('='*50)
s = 0
agent, c, _ = send(token, '详细教我Python装饰器，包含代码示例、常见错误和练习题', timeout=90)
print('Agent: {} | Chars: {}'.format(agent, len(c)))
s += P(len(c)>500, 'Over 500 chars ({})'.format(len(c)))
s += P('```' in c, 'Code blocks present')
s += P(any(kw in c for kw in ['练习','题目','试试','挑战','exercise']), 'Exercises included')
s += P(any(kw in c for kw in ['陷阱','注意','错误','误区','不要','常见']), 'Pitfalls covered')
s += P(any(kw in c for kw in ['下一步','接下来','继续','进阶','进一步']), 'Next steps guidance')
s += P(any(kw in c.lower() for kw in ['应用','场景','日志','实际','项目','timer','log','auth']), 'Real-world context')
# Show content snippet
print('  Content snippet: {}...'.format(c[200:500] if len(c)>200 else c[:200]))
total += s; max_s += 6
print('  Score: {}/6\n'.format(s))

# ====== 4. Resource auto-generation & storage ======
print('='*50)
print('TEST 4: Resource auto-generation to DB')
print('='*50)
s = 0
for msg in ['生成Python列表的思维导图', '写Python文件读写的完整代码']:
    agent, c, _ = send(token, msg, timeout=45)
    print('  {:40s} -> {} ({} chars)'.format(msg[:40], agent, len(c)))
time.sleep(1)
resources = api_get(token, '/api/resources')
res_list = resources if isinstance(resources, list) else resources.get('items',[])
s += P(len(res_list)>=2, 'At least 2 resources saved ({})'.format(len(res_list)))
types = set(r.get('resource_type','') for r in res_list)
s += P(len(types)>=2, 'Multiple resource types ({} types)'.format(len(types)))
print('  Resources: {} | Types: {}'.format(len(res_list), types))
total += s; max_s += 2
print('  Score: {}/2\n'.format(s))

# ====== 5. Multi-turn context ======
print('='*50)
print('TEST 5: Multi-turn context understanding')
print('='*50)
s = 0
a1, c1, _ = send(token, '我在学Python面向对象，不太理解继承和多态')
print('  Turn1: {} ({} chars)'.format(a1, len(c1)))
a2, c2, _ = send(token, '能给我一个代码例子说明它怎么用吗')
has_ctx = any(kw in c2.lower() for kw in ['继承','inherit','多态','polymorph','class','super','子类','父类'])
s += P(has_ctx, 'Pronoun resolution (it -> inheritance/polymorphism)')
print('  Turn2: {} ({} chars)'.format(a2, len(c2)))
a3, c3, _ = send(token, '那super()在这里面起什么作用')
has_s = 'super()' in c3 or 'super' in c3.lower()
s += P(has_s, 'Context maintained (super() covered)')
print('  Turn3: {} ({} chars)'.format(a3, len(c3)))
total += s; max_s += 2
print('  Score: {}/2\n'.format(s))

# ====== 6. Assessment report quality ======
print('='*50)
print('TEST 6: Assessment report personalization')
print('='*50)
s = 0
agent, c, _ = send(token, '给我做一份详细的Python学习评估报告', timeout=90)
print('Agent: {} | Chars: {}'.format(agent, len(c)))
s += P(len(c)>400, 'Detailed report ({} chars)'.format(len(c)))
s += P(any(kw in c for kw in ['分','掌握','水平','得分','评价']), 'Quantified scores')
s += P(any(kw in c for kw in ['优势','强项','掌握好','擅长','不错']), 'Strengths identified')
s += P(any(kw in c for kw in ['薄弱','不足','改进','加强','弱点','短板']), 'Weaknesses identified')
s += P(any(kw in c for kw in ['建议','推荐','下一步','计划','策略']), 'Improvement suggestions')
reports = api_get(token, '/api/assessment/reports')
rep_list = reports if isinstance(reports, list) else reports.get('items',[])
s += P(len(rep_list)>0, 'Report saved to DB ({} reports)'.format(len(rep_list)))
# Show snippet
print('  Content snippet: {}...'.format(c[100:400] if len(c)>100 else c[:200]))
total += s; max_s += 6
print('  Score: {}/6\n'.format(s))

# ====== FINAL ======
print('='*50)
print('FINAL SCORE')
print('='*50)
pct = total/max_s*100
print('Total: {}/{} ({:.0f}%)'.format(total, max_s, pct))
print('Provincial First Prize Threshold: 85%')
print('Status: {}'.format('PASS' if pct>=85 else 'NEED IMPROVEMENT'))
