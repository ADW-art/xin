import urllib.request as R, json, time, sys
sys.stdout.reconfigure(line_buffering=True)

# Register
d=json.dumps({'username':'s_fast99','password':'test123'}).encode()
r=R.urlopen(R.Request('http://127.0.0.1:8003/api/auth/register',data=d,headers={'Content-Type':'application/json'},method='POST'),timeout=10)
tk=json.loads(r.read()).get('access_token','')
print(f'Registered, token: {bool(tk)}')
sys.stdout.flush()

# Chat
t0=time.time()
d=json.dumps({'content':'你好'}).encode()
req=R.Request('http://127.0.0.1:8003/api/chat/send',data=d,
    headers={'Content-Type':'application/json','Authorization':f'Bearer {tk}'},method='POST')
r=R.urlopen(req,timeout=60)
body=r.read().decode()
ms=int((time.time()-t0)*1000)
print(f'Chat: {r.status}, {ms}ms, {len(body)} chars')
print('First 400 chars:')
print(body[:400])
sys.stdout.flush()
