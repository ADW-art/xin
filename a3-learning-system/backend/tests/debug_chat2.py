import urllib.request as R, json

# Register
data = json.dumps({'username':'s_debug2','password':'test123'}).encode()
r = R.urlopen(R.Request('http://127.0.0.1:8003/api/auth/register', data=data, headers={'Content-Type':'application/json'}, method='POST'), timeout=15)
resp = json.loads(r.read())
token = resp.get('access_token','')
print('Token OK:', bool(token))

# Chat (correct field name: content)
data = json.dumps({'content': '你好'}).encode()
req = R.Request('http://127.0.0.1:8003/api/chat/send', data=data,
    headers={'Content-Type':'application/json','Authorization': f'Bearer {token}'},
    method='POST')
r = R.urlopen(req, timeout=90)
body = r.read().decode()
print(f'Status: {r.status}')
print(f'Content-Type: {r.headers.get("Content-Type","?")}')
print('=== RAW (first 2000 chars) ===')
print(body[:2000])
print('=== END ===')
print(f'Total length: {len(body)}')
