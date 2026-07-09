import requests, json, io, sys, time, string, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://localhost:8001'
total = 0; passed = 0
def T(ok, label):
    global total, passed
    total += 1
    if ok: passed += 1
    print('  {} {}'.format('PASS' if ok else 'FAIL', label))

uid = ''.join(random.choices(string.digits, k=4))
r = requests.post(BASE+'/api/auth/register', json={'username':'rep'+uid,'password':'test123','nickname':'FR'})
token = r.json()['access_token']
h = {'Authorization': 'Bearer {}'.format(token), 'Content-Type': 'application/json'}

def stream_read(r, timeout=60):
    """Read full SSE stream"""
    body = b''
    try:
        for c in r.iter_content(chunk_size=None, decode_unicode=False):
            if c: body += c
    except: pass
    return body.decode('utf-8', 'replace')

print('='*50)
print('A3 全面实装测试')
print('='*50)

# 1. Profile-First
print('\n1. Profile-First Collection')
text = stream_read(requests.post(BASE+'/api/chat/send', headers=h, json={'content':'我想学Python装饰器','images':None}, stream=True, timeout=60))
T('profile_agent' in text, 'Routes to profile_agent')
time.sleep(1)

stream_read(requests.post(BASE+'/api/chat/send', headers=h, json={'content':'我学过C，Python工作，每周20小时，动手实践','images':None}, stream=True, timeout=60))
time.sleep(1)

r = requests.get(BASE+'/api/profile/me', headers=h)
if r.status_code==200 and r.text.strip():
    p = r.json()
    dims = sum(1 for k in ['knowledge_base','learning_goal','weekly_hours'] if p.get(k))
    T(dims>=2, 'Profile {}/3 dims (goal={} hours={})'.format(dims, p.get('learning_goal'), p.get('weekly_hours')))
else:
    T(False, 'Profile API {}'.format(r.status_code))

# 2. Agent Routing
print('\n2. Agent Routing (6 intents)')
tests = [('Python闭包原理','resource_agent'),('写归并排序代码','resource_agent'),('出3道Python算法题','question_agent'),('Python学习评估报告','evaluation_agent'),('Python学习路线','path_agent'),('你好今天天气不错','chat_agent')]
ok = 0
for msg, exp in tests:
    text = stream_read(requests.post(BASE+'/api/chat/send', headers=h, json={'content':msg,'images':None}, stream=True, timeout=45))
    if exp in text: ok += 1
    time.sleep(0.3)
T(ok >= 5, '{}/{} routes correct'.format(ok, len(tests)))

# 3. Resources
print('\n3. Resource Auto-Save')
r = requests.get(BASE+'/api/resources', headers=h)
res = r.json() if r.status_code==200 else []
rc = len(res) if isinstance(res,list) else len(res.get('items',[]))
T(rc > 0, '{} resources saved to DB'.format(rc))

# 4. BKT
print('\n4. BKT Knowledge Tracing')
r = requests.get(BASE+'/api/bkt/status', headers=h)
b = r.json() if r.status_code==200 else {}
cc = len(b.get('concepts',[]))
T(cc > 0, '{} concepts tracked'.format(cc))

# 5. Assessment
print('\n5. Assessment Report')
text = stream_read(requests.post(BASE+'/api/chat/send', headers=h, json={'content':'给我做Python学习评估报告','images':None}, stream=True, timeout=90))
T(len(text) > 500, 'Report {} chars'.format(len(text)))
T('mermaid' in text.lower(), 'Mermaid diagram embedded')
time.sleep(1)
r = requests.get(BASE+'/api/assessment/reports', headers=h)
reps = r.json() if r.status_code==200 else []
rc2 = len(reps) if isinstance(reps,list) else len(reps.get('items',[]))
T(rc2 > 0, '{} reports saved to DB'.format(rc2))

# 6. Learning Path
print('\n6. Learning Path')
r = requests.get(BASE+'/api/path/current', headers=h)
path = r.json() if r.status_code==200 else {}
ph = len(path.get('phases',[]))
T(ph > 0, '{} DAG phases'.format(ph))

# 7. TTS
print('\n7. TTS Voice Synthesis')
r = requests.post(BASE+'/api/tts/synthesize', headers=h, json={'text':'Python装饰器是一种特殊函数','voice':'xiaoyan'})
T(r.status_code in (200,503), 'TTS API HTTP {} (200=avail, 503=no key)'.format(r.status_code))

# 8. Code Quality
print('\n8. Code Quality')
text = stream_read(requests.post(BASE+'/api/chat/send', headers=h, json={'content':'写一个二分查找代码','images':None}, stream=True, timeout=45))
T('```' in text, 'Code blocks present')
T('# 输出：' not in text, 'No hallucinated #output comments')
T('<span class=' not in text, 'No raw HTML tags in output')

# 9. Chat History
print('\n9. Chat History & Delete')
r = requests.get(BASE+'/api/chat/history?limit=10', headers=h)
hist = r.json() if r.status_code==200 else []
hc = len(hist) if isinstance(hist,list) else len(hist.get('items',[]))
T(hc > 0, '{} history items'.format(hc))
if isinstance(hist,list) and hist:
    r = requests.delete(BASE+'/api/chat/history/{}'.format(hist[0].get('id')), headers=h)
    T(r.status_code==200, 'Single item delete OK')

# 10. SSE Events
print('\n10. SSE Event Types')
text = stream_read(requests.post(BASE+'/api/chat/send', headers=h, json={'content':'谢谢','images':None}, stream=True, timeout=30))
event_types = ['agent_switch','message','progress','done']
found_all = all(et in text for et in event_types)
T(found_all, 'All event types present: {}'.format([et for et in event_types if et in text]))

# SUMMARY
print('\n' + '='*50)
pct = passed/total*100
print('RESULT: {}/{} ({:.0f}%)'.format(passed, total, pct))
if pct >= 80: print('省一标准: ✅ 达标 (>=80%)')
else: print('省一标准: ❌ 需改进 (<80%)')
