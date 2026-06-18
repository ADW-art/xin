import urllib.request as R, json
data = json.dumps({'username':'s_test_temp','password':'test123'}).encode()
r = R.urlopen(R.Request('http://127.0.0.1:8001/api/auth/register', data=data, headers={'Content-Type':'application/json'}, method='POST'), timeout=15)
resp = json.loads(r.read())
token = resp.get('access_token','')
print('Token:', token[:40] if token else 'NONE')

data = json.dumps({'message': '你好'}).encode()
req = R.Request('http://127.0.0.1:8001/api/chat/send', data=data,
    headers={'Content-Type':'application/json','Authorization': f'Bearer {token}','Accept':'text/event-stream'},
    method='POST')
r = R.urlopen(req, timeout=30)
body = r.read().decode()
print('=== RAW SSE (first 1000 chars) ===')
print(body[:1000])
print('=== END ===')
