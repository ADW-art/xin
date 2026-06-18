import urllib.request as R, json, time, sys

BASE = "http://127.0.0.1:8003"
TS = str(int(time.time()))[-6:]

def api(method, path, data=None, token=None, timeout=30):
    url=f"{BASE}{path}"
    h={"Content-Type":"application/json"}
    if token: h["Authorization"]=f"Bearer {token}"
    body=json.dumps(data).encode() if data else None
    req=R.Request(url,data=body,headers=h,method=method)
    try:
        resp=R.urlopen(req,timeout=timeout)
        return resp.status, json.loads(resp.read().decode())
    except Exception as e:
        return 0, {"error":str(e)}

def register(name):
    st,d=api("POST","/api/auth/register",{"username":f"{name}_{TS}","password":"test123"})
    if st==200: return d.get("access_token","")
    st2,d2=api("POST","/api/auth/login",{"username":f"{name}_{TS}","password":"test123"})
    return d2.get("access_token","") if st2==200 else ""

def chat(msg,token,timeout=120):
    data=json.dumps({"content":msg}).encode()
    r=R.urlopen(R.Request(f"{BASE}/api/chat/send",data=data,
        headers={"Content-Type":"application/json","Authorization":f"Bearer {token}"},method="POST"),timeout=timeout)
    body=r.read().decode()
    text=""
    for line in body.split("\n"):
        if line.startswith("data: "):
            try:
                ev=json.loads(line[6:])
                if "content" in ev: text+=ev["content"]
            except: pass
    return text

t = register("qc")
print("=== Question Generation ===\n")
txt = chat("出3道Python基础选择题，每题4个选项，标明正确答案", t)
print(txt[:600])
print(f"\n[Length: {len(txt)} chars]")

print("\n=== Learning Path Content ===\n")
st,p = api("GET","/api/path/current",token=t)
print(f"Status: {st}")
if st==200 and p:
    import json as j
    print(j.dumps(p, ensure_ascii=False)[:600])

print("\n=== BKT Status with Correct Field ===\n")
for i,(qid,c,kp) in enumerate([(1,True,"变量"),(2,False,"循环"),(3,True,"函数")]):
    st,d=api("POST","/api/bkt/answer",{"question_id":qid,"user_answer":"A","is_correct":c,"time_spent":30,"concept":kp,"difficulty":1},t)
    print(f"Ans{i+1} ({'OK' if c else 'X'} on {kp}): status={st}")
st,b=api("GET","/api/bkt/status",token=t)
try:
    for c in b.get("concepts",[]):
        print(f"  {c['name']}: p_known={c['p_known']:.4f}, level={c['level']}")
    print(f"  Avg: {b.get('average_mastery','?')}, Mastered: {b.get('mastered_count','?')}")
except: print(f"  Raw: {str(b)[:300]}")

print("\n=== Conversation History at Correct Path ===\n")
st,h=api("GET","/api/chat/history",token=t)
print(f"/api/chat/history: status={st}, msgs={len(h) if isinstance(h,list) else '?'}")

print("\n=== Profile Status ===\n")
st,p=api("GET","/api/profile/me",token=t)
try:
    ds=p.get("dimension_scores",{})
    print(f"Dimensions: {len(ds)}")
    for k,v in ds.items():
        print(f"  {k}: {v}")
except: print(f"Raw: {str(p)[:300]}")
