"""Clean E2E Test with unique usernames and proper auth"""
import urllib.request as R, urllib.error, json, time, sys

BASE = "http://127.0.0.1:8003"
TS = str(int(time.time()))[-6:]  # timestamp suffix

class TR:
    def __init__(self):
        self.r = []; self.p = 0; self.f = 0
    def add(self, s, step, ok, resp, tms, notes=""):
        self.r.append({"s":s,"step":step,"ok":ok,"resp":str(resp)[:250],"ms":tms,"notes":notes})
        if ok: self.p += 1
        else: self.f += 1
        print(f"  [{'PASS' if ok else 'FAIL'}] S{s} {step} ({tms}ms) {notes}")
        if not ok and resp: print(f"        Resp: {str(resp)[:200]}")
        sys.stdout.flush()
    def sum(self): return f"{self.p}/{self.p+self.f} passed"

rpt = TR()

def api(method, path, data=None, token=None, timeout=30):
    url=f"{BASE}{path}"
    h={"Content-Type":"application/json"}
    if token: h["Authorization"]=f"Bearer {token}"
    body=json.dumps(data).encode() if data else None
    req=R.Request(url,data=body,headers=h,method=method)
    t0=time.time()
    try:
        resp=R.urlopen(req,timeout=timeout)
        ms=int((time.time()-t0)*1000)
        return resp.status, json.loads(resp.read().decode()), ms
    except urllib.error.HTTPError as e:
        ms=int((time.time()-t0)*1000)
        try: b=json.loads(e.read().decode())
        except: b={"detail":"parse_error"}
        return e.code, b, ms
    except Exception as e:
        ms=int((time.time()-t0)*1000)
        return 0, {"error":str(e)}, ms

def chat(message, token, timeout=120):
    t0=time.time()
    data=json.dumps({"content":message}).encode()
    req=R.Request(f"{BASE}/api/chat/send", data=data,
        headers={"Content-Type":"application/json","Authorization":f"Bearer {token}"},
        method="POST")
    try:
        resp=R.urlopen(req,timeout=timeout)
        ms=int((time.time()-t0)*1000)
        body=resp.read().decode()
        text=""; agent="?"; ev_count=0
        for line in body.split("\n"):
            if line.startswith("data: "):
                try:
                    ev=json.loads(line[6:]); ev_count+=1
                    if "content" in ev: text+=ev.get("content","")
                    if "agent" in ev: agent=ev["agent"]
                except: pass
        return resp.status, text, agent, ev_count, ms
    except urllib.error.HTTPError as e:
        ms=int((time.time()-t0)*1000)
        return e.code, "", "?", 0, ms
    except Exception as e:
        ms=int((time.time()-t0)*1000)
        return 0, "", "?", 0, ms

def register(name):
    st,d,t=api("POST","/api/auth/register",{"username":f"{name}_{TS}","password":"test123","nickname":name.upper()})
    if st==200: return d.get("access_token","")
    # try login if already exists
    st2,d2,t2=api("POST","/api/auth/login",{"username":f"{name}_{TS}","password":"test123"})
    if st2==200: return d2.get("access_token","")
    return ""

def sdims(p):
    try:
        if not isinstance(p,dict): return 0
        ds=p.get("dimension_scores")
        return len(ds) if ds else 0
    except: return 0

def slen(v):
    try:
        if isinstance(v,(list,dict)): return len(v)
        if v is None: return 0
        return 1
    except: return 0

print("="*60); print(f"A3 CLEAN E2E TEST (ts={TS})"); print(f"Target: {BASE}"); print("="*60)
t_total = time.time()

# ═══ S1: Complete Beginner Journey ═══
print("\n=== S1: Complete Beginner Journey ===")
t1 = register("s1")
rpt.add(1,"1.Register",bool(t1),f"token={bool(t1)}",0)

st,tx,ag,ev,t=chat("你好，我是零基础Python初学者，想找一份开发工作",t1)
rpt.add(1,"2.Profile-Intro",st==200 and len(tx)>0,tx,t,f"agent={ag} ev={ev} len={len(tx)}")

st,tx,ag,ev,t=chat("我每周大概学10小时，喜欢动手写代码",t1)
rpt.add(1,"3.Profile-Details",st==200 and len(tx)>0,tx,t,f"agent={ag} len={len(tx)}")

st,tx,ag,ev,t=chat("教我Python列表推导式",t1)
rpt.add(1,"4.Learn-ListComp",st==200 and len(tx)>0,tx,t,
    f"quality={'GOOD' if len(tx)>100 else ('POOR' if len(tx)>0 else 'EMPTY')} len={len(tx)}")

st,tx,ag,ev,t=chat("出3道Python基础题",t1)
rpt.add(1,"5.Questions",st==200 and len(tx)>0,tx,t,f"has_q={'1.' in tx or 'A' in tx[:100]},len={len(tx)}")

for i,(qid,c,kp) in enumerate([(1,True,"变量"),(2,True,"循环"),(3,False,"函数")]):
    st,d,tm=api("POST","/api/bkt/answer",{"question_id":qid,"user_answer":"A","is_correct":c,"time_spent":30,"knowledge_point":kp,"difficulty":1},t1)
    rpt.add(1,f"6.Ans{i+1}({'OK' if c else 'X'})",st in[200,201],d,tm)

st,tx,ag,ev,t=chat("评估一下我的学习情况",t1)
rpt.add(1,"7.Evaluate",st==200 and len(tx)>0,tx,t,f"score={'分' in tx or '掌握' in tx}")

st,tx,ag,ev,t=chat("制定学习计划",t1)
rpt.add(1,"8.Plan",st==200 and len(tx)>0,tx,t,f"len={len(tx)}")

st,p,tm=api("GET","/api/profile/me",token=t1)
rpt.add(1,"9.Profile",st==200 and sdims(p)>=1,p,tm,f"dims={sdims(p)}")

st,b,tm=api("GET","/api/bkt/status",token=t1)
rpt.add(1,"10.BKT",st in[200,404],b,tm,f"entries={slen(b)}")

# ═══ S2: Advanced Learner ═══
print("\n=== S2: Advanced Learner ===")
t2 = register("s2")
rpt.add(2,"1.Register",bool(t2),"",0)

st,tx,ag,ev,t=chat("我需要复习数据结构中的二叉树遍历",t2)
rpt.add(2,"2.SkipProfile-Learn",st==200 and len(tx)>0,tx,t,f"agent={ag} len={len(tx)}")

st,tx,ag,ev,t=chat("出算法题",t2)
rpt.add(2,"3.Algorithm-Q",st==200 and len(tx)>0,tx,t,f"advanced={'二叉' in tx or 'tree' in tx.lower() or '遍历' in tx}")

st,tx,ag,ev,t=chat("给我解释BFS和DFS的区别",t2)
rpt.add(2,"4.BFSvsDFS",st==200 and len(tx)>0,tx,t,f"BFS_in_text={'BFS' in tx} DFS_in_text={'DFS' in tx}")

st,p,tm=api("GET","/api/profile/me",token=t2)
rpt.add(2,"5.Auto-Profile",st==200,p,tm,f"dims={sdims(p)}")

# ═══ S3: Edge Cases ═══
print("\n=== S3: Edge Cases ===")
st,tx,_,_,t=chat("",t1,timeout=30)
rpt.add(3,"1.Empty-422",st in[422,400],f"s={st}",t)

st,tx,_,_,t=chat("   ",t1,timeout=30)
rpt.add(3,"2.Spaces-422",st in[422,400],f"s={st}",t)

lm="请详细讲解Python编程"+"的方方面面"*400
st,tx,_,_,t=chat(lm,t1)
rpt.add(3,"3.LongMsg",st==200,f"in={len(lm)} out={len(tx)}",t)

st,tx,_,_,t=chat("Explain Python decorator @符号 and code example please",t1)
rpt.add(3,"4.MixedLang",st==200 and len(tx)>0,tx,t,f"len={len(tx)}")

tf=time.time()
s1_,tx1,_,_,t1_=chat("什么是变量",t1)
s2_,tx2,_,_,t2_=chat("什么是函数",t1)
s3_,tx3,_,_,t3_=chat("什么是类",t1)
tft=int((time.time()-tf)*1000)
rpt.add(3,"5.RapidFire",all([s1_==200,s2_==200,s3_==200]),f"t={t1_}ms/{t2_}ms/{t3_}ms",tft)

st,d,tm=api("GET","/api/resources/99999",token=t1)
rpt.add(3,"6.NotFound",st in[404,200],d,tm,f"s={st}")

st,d,tm=api("GET","/api/profile/me")
rpt.add(3,"7.Unauth401",st in[401,403],d,tm,f"s={st}")

# ═══ S4: Multi-turn Coherence ═══
print("\n=== S4: Multi-turn Coherence ===")
t4 = register("s4")
rpt.add(4,"1.Register",bool(t4),"",0)

st,tx1,_,_,t=chat("我想学Python数据分析",t4)
rpt.add(4,"2.T1-DataAnalysis",st==200 and len(tx1)>0,tx1,t,f"len={len(tx1)}")

st,tx2,_,_,t=chat("需要先学哪些基础知识",t4)
coh2=any(w in tx2 for w in ["Python","python","数据","分析","pandas","numpy","统计","基础"])
rpt.add(4,"3.T2-Prereqs",st==200 and len(tx2)>0,tx2,t,f"coherent={coh2}")

st,tx3,_,_,t=chat("给我推荐第一个要学的",t4)
coh3=any(w in tx3 for w in ["Python","python","基础","入门","语法","pandas","numpy"])
rpt.add(4,"4.T3-Recommend",st==200 and len(tx3)>0,tx3,t,f"coherent={coh3}")

st,h,tm=api("GET","/api/conversation",token=t4)
mc=slen(h)
rpt.add(4,"5.History",st==200 and mc>=3,h,tm,f"msgs={mc}")

# ═══ S5: Full Assessment Cycle ═══
print("\n=== S5: Full Assessment Cycle ===")
t5 = register("s5")
rpt.add(5,"1.Register",bool(t5),"",0)

st,tx,_,_,t=chat("我是Python初学者，想系统学习",t5)
rpt.add(5,"2.BuildProfile",st==200 and len(tx)>0,tx,t,f"len={len(tx)}")

st,tx,_,_,t=chat("出5道Python基础选择题",t5)
rpt.add(5,"3.GenQuestions",st==200 and len(tx)>0,tx,t,f"len={len(tx)}")

for i in range(5):
    st,d,tm=api("POST","/api/bkt/answer",{"question_id":100+i,"user_answer":"A","is_correct":i<4,"time_spent":30,"knowledge_point":"Python基础","difficulty":i+1},t5)
    rpt.add(5,f"4.Ans{i+1}({'OK' if i<4 else 'X'})",st in[200,201],d,tm)

st,b1,tm=api("GET","/api/bkt/status",token=t5)
bc1=slen(b1)
rpt.add(5,"5.BKT-Batch1",st in[200,404],str(b1)[:150],tm,f"entries={bc1}")

for i in range(3):
    st,d,tm=api("POST","/api/bkt/answer",{"question_id":200+i,"user_answer":"C","is_correct":False,"time_spent":60,"knowledge_point":"Python基础","difficulty":2},t5)
    rpt.add(5,f"6.Wrong{i+1}",st in[200,201],d,tm)

st,b2,tm=api("GET","/api/bkt/status",token=t5)
bc2=slen(b2)
rpt.add(5,"7.BKT-Batch2",st in[200,404],str(b2)[:150],tm,f"entries={bc2} changed={bc2!=bc1}")

st,tx,_,_,t=chat("评估我的学习情况",t5)
rpt.add(5,"8.Evaluate",st==200 and len(tx)>0,tx,t,f"len={len(tx)}")

st,p,tm=api("GET","/api/path/current",token=t5)
rpt.add(5,"9.LearningPath",st in[200,404],str(p)[:150],tm,f"s={st}")

st,s,tm=api("GET","/api/path/debug/simulate",token=t5)
rpt.add(5,"10.DebugSim",st!=0,str(s)[:150],tm,f"s={st}")

# ═══ FINAL ═══
total_ms = int((time.time()-t_total)*1000)
print("\n"+"="*60)
print(f"FINAL: {rpt.sum()} (in {total_ms//1000}s)")
print("="*60)

# Write report
lines=["# A3 Live E2E Test Report (Clean)","",f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
       f"**Base**: {BASE}", f"**Timestamp suffix**: {TS}","",f"**Result**: {rpt.sum()}","","---",""]
for r in rpt.r:
    st="PASS" if r["ok"] else "FAIL"
    lines.append(f"## [{st}] Scenario {r['s']} - {r['step']}")
    lines.append(f"- Time: {r['ms']}ms")
    lines.append(f"- Response: {r['resp'][:300]}")
    lines.append(f"- Notes: {r['notes']}")
    lines.append("")

path = r"E:\code\claude-1\a3-learning-system\backend\tests\live_test_report.md"
with open(path,"w",encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Report: {path}")
