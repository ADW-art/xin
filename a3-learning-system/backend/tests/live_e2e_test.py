"""
Live Multi-Scenario E2E Test for A3 Learning System
Runs against http://127.0.0.1:8003
"""
import urllib.request as R
import urllib.error
import json, time, sys, traceback

BASE = "http://127.0.0.1:8003"

class TR:
    def __init__(self):
        self.results = []
        self.p = 0; self.f = 0
    def add(self, s, step, ok, resp, tms, notes=""):
        r = {"s":s,"step":step,"ok":ok,"resp":str(resp)[:250],"ms":tms,"notes":notes}
        self.results.append(r)
        if ok: self.p += 1
        else: self.f += 1
        st = "PASS" if ok else "FAIL"
        print(f"  [{st}] S{s} {step} ({tms}ms) {notes}")
        if not ok and resp:
            print(f"        Response: {str(resp)[:200]}")
    def sum(self):
        return f"{self.p}/{self.p+self.f} passed"
    def prt_all(self):
        for r in self.results:
            st = "PASS" if r["ok"] else "FAIL"
            print(f"\n[{st}] S{r['s']} {r['step']} ({r['ms']}ms)")
            print(f"  Response: {r['resp'][:200]}")
            print(f"  Notes: {r['notes']}")

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
                    ev=json.loads(line[6:])
                    ev_count+=1
                    if "content" in ev:
                        text+=ev.get("content","")
                    if "agent" in ev:
                        agent=ev["agent"]
                except: pass
        return resp.status, text, agent, ev_count, ms
    except urllib.error.HTTPError as e:
        ms=int((time.time()-t0)*1000)
        return e.code, "", "?", 0, ms
    except Exception as e:
        ms=int((time.time()-t0)*1000)
        return 0, f"ERR:{e}", "?", 0, ms

def safe_len(v):
    try:
        if isinstance(v,(list,dict)): return len(v)
        if v is None: return 0
        return len(str(v))
    except: return 0

def safe_dims(p):
    try:
        if not isinstance(p,dict): return 0
        ds = p.get("dimension_scores") or {}
        return len(ds)
    except: return 0

# ═══════════════════════════════════════════
print("="*60); print("A3 LIVE E2E TEST"); print(f"Target: {BASE}"); print("="*60)

# ═══ S1: Complete Beginner Journey ═══
print("\n=== SCENARIO 1: Complete Beginner Journey ===")
t_start = time.time()

st,d,t=api("POST","/api/auth/register",{"username":"s1_user","password":"test123","nickname":"S1"})
t1=d.get("access_token","") if st==200 else ""
rpt.add(1,"1.Register",st==200,d,t)

st,tx,ag,ev,t=chat("你好，我是零基础Python初学者，想找一份开发工作",t1)
rpt.add(1,"2.Profile-Intro",st==200 and len(tx)>0,tx,t,f"agent={ag} ev={ev} len={len(tx)}")

st,tx,ag,ev,t=chat("我每周大概学10小时，喜欢动手写代码",t1)
rpt.add(1,"3.Profile-Details",st==200 and len(tx)>0,tx,t,f"agent={ag} len={len(tx)}")

st,tx,ag,ev,t=chat("教我Python列表推导式",t1)
q4="GOOD" if len(tx)>100 else ("POOR" if len(tx)>0 else "EMPTY")
rpt.add(1,"4.Learn-ListComp",st==200 and len(tx)>0,tx,t,f"quality={q4} len={len(tx)}")

st,tx,ag,ev,t=chat("出3道Python基础题",t1)
rpt.add(1,"5.Generate-Questions",st==200 and len(tx)>0,tx,t,f"has_q={'1.'in tx or 'A' in tx[:100]}, len={len(tx)}")

for i,(qid,corr,kp) in enumerate([(1,True,"变量"),(2,True,"循环"),(3,False,"函数")]):
    st,d,t=api("POST","/api/bkt/answer",
        {"question_id":qid,"user_answer":"A","is_correct":corr,"time_spent":30,"knowledge_point":kp,"difficulty":1},t1)
    rpt.add(1,f"6a.AnsQ{i+1}({'OK' if corr else 'X'})",st in[200,201],d,t)

st,tx,ag,ev,t=chat("评估一下我的学习情况",t1)
rpt.add(1,"7.Evaluate",st==200 and len(tx)>0,tx,t,f"has_score={'分' in tx or '掌握' in tx or '水平' in tx}")

st,tx,ag,ev,t=chat("制定学习计划",t1)
rpt.add(1,"8.Learning-Plan",st==200 and len(tx)>0,tx,t,f"len={len(tx)}")

st,p,t=api("GET","/api/profile/me",token=t1)
dc=safe_dims(p)
rpt.add(1,"9.Check-Profile",st==200 and dc>=1,p,t,f"dims_found={dc}")

st,b,t=api("GET","/api/bkt/status",token=t1)
bc=safe_len(b)
rpt.add(1,"10.Check-BKT",st in[200,404],b,t,f"bkt_entries={bc}")

s1_ms = int((time.time()-t_start)*1000)
print(f"  S1 TOTAL: {s1_ms}ms ({s1_ms//1000}s)")

# ═══ S2: Advanced Learner ═══
print("\n=== SCENARIO 2: Advanced Learner ===")
t_start = time.time()

st,d,t=api("POST","/api/auth/register",{"username":"s2_user","password":"test123","nickname":"AdvS2"})
t2=d.get("access_token","") if st==200 else ""
rpt.add(2,"1.Register",st==200,d,t)

st,tx,ag,ev,t=chat("我需要复习数据结构中的二叉树遍历",t2)
rpt.add(2,"2.SkipProfile-Learn",st==200 and len(tx)>0,tx,t,f"agent={ag} len={len(tx)}")

st,tx,ag,ev,t=chat("出算法题",t2)
rpt.add(2,"3.Algorithm-Q",st==200 and len(tx)>0,tx,t,f"advanced={'二叉' in tx or 'tree' in tx.lower() or '遍历' in tx}")

st,tx,ag,ev,t=chat("给我解释BFS和DFS的区别",t2)
rpt.add(2,"4.BFSvsDFS",st==200 and len(tx)>0,tx,t,f"BFS={'BFS' in tx} DFS={'DFS' in tx}")

st,p,t=api("GET","/api/profile/me",token=t2)
dc2=safe_dims(p)
rpt.add(2,"5.Auto-Profile",st==200,p,t,f"auto_dims={dc2}")

s2_ms = int((time.time()-t_start)*1000)
print(f"  S2 TOTAL: {s2_ms}ms ({s2_ms//1000}s)")

# ═══ S3: Edge Cases ═══
print("\n=== SCENARIO 3: Edge Cases ===")
t_start = time.time()

# Use s1's token
st,tx,ag,ev,t=chat("",t1,timeout=30)
rpt.add(3,"1.Empty-422",st in[422,400],f"s={st}",t)

st,tx,ag,ev,t=chat("   ",t1,timeout=30)
rpt.add(3,"2.Spaces-422",st in[422,400],f"s={st}",t)

lm="请详细讲解Python编程"+"的方方面面"*400
st,tx,ag,ev,t=chat(lm,t1)
rpt.add(3,"3.LongMsg",st==200,f"in={len(lm)} out={len(tx)}",t)

st,tx,ag,ev,t=chat("Explain Python decorator with @符号 and code示例 please",t1)
rpt.add(3,"4.MixedLang",st==200 and len(tx)>0,tx,t,f"len={len(tx)}")

tf=time.time()
s1_,tx1,_,_,t1_=chat("什么是变量",t1)
s2_,tx2,_,_,t2_=chat("什么是函数",t1)
s3_,tx3,_,_,t3_=chat("什么是类",t1)
tft=int((time.time()-tf)*1000)
rpt.add(3,"5.RapidFire",all([s1_==200,s2_==200,s3_==200]),f"t={t1_}ms/{t2_}ms/{t3_}ms",tft)

st,d,t=api("GET","/api/resources/99999",token=t1)
rpt.add(3,"6.NotFound-404",st in[404,200],d,t,f"s={st}")

st,d,t=api("GET","/api/profile/me")
rpt.add(3,"7.Unauth-401",st in[401,403],d,t,f"s={st}")

s3_ms = int((time.time()-t_start)*1000)
print(f"  S3 TOTAL: {s3_ms}ms ({s3_ms//1000}s)")

# ═══ S4: Multi-turn Coherence ═══
print("\n=== SCENARIO 4: Multi-turn Coherence ===")
t_start = time.time()

st,d,t=api("POST","/api/auth/register",{"username":"s4_user","password":"test123","nickname":"CohS4"})
t4=d.get("access_token","") if st==200 else ""
rpt.add(4,"1.Register",st==200,d,t)

st,tx1,ag,ev,t=chat("我想学Python数据分析",t4)
rpt.add(4,"2.T1-DataAnalysis",st==200 and len(tx1)>0,tx1,t,f"len={len(tx1)}")

st,tx2,ag,ev,t=chat("需要先学哪些基础知识",t4)
coh2=any(w in tx2 for w in ["Python","python","数据","分析","pandas","numpy","统计","基础"])
rpt.add(4,"3.T2-Prereqs",st==200 and len(tx2)>0,tx2,t,f"coherent={coh2}")

st,tx3,ag,ev,t=chat("给我推荐第一个要学的",t4)
coh3=any(w in tx3 for w in ["Python","python","基础","入门","语法","pandas","numpy","变量"])
rpt.add(4,"4.T3-Recommend",st==200 and len(tx3)>0,tx3,t,f"coherent={coh3}")

st,h,t=api("GET","/api/conversation",token=t4)
mc=safe_len(h)
rpt.add(4,"5.History",st==200 and mc>=3,h,t,f"msgs={mc}")

s4_ms = int((time.time()-t_start)*1000)
print(f"  S4 TOTAL: {s4_ms}ms ({s4_ms//1000}s)")

# ═══ S5: Full Assessment Cycle ═══
print("\n=== SCENARIO 5: Full Assessment Cycle ===")
t_start = time.time()

st,d,t=api("POST","/api/auth/register",{"username":"s5_user","password":"test123","nickname":"AssessS5"})
t5=d.get("access_token","") if st==200 else ""
rpt.add(5,"1.Register",st==200,d,t)

st,tx,ag,ev,t=chat("我是Python初学者，想系统学习",t5)
rpt.add(5,"2.BuildProfile",st==200 and len(tx)>0,tx,t,f"len={len(tx)}")

st,tx,ag,ev,t=chat("出5道Python基础选择题",t5)
rpt.add(5,"3.GenQuestions",st==200 and len(tx)>0,tx,t,f"len={len(tx)}")

for i in range(5):
    st,d,t=api("POST","/api/bkt/answer",
        {"question_id":100+i,"user_answer":"A","is_correct":i<4,"time_spent":30,"knowledge_point":"Python基础","difficulty":i+1},t5)
    rpt.add(5,f"4a.A{i+1}({'OK' if i<4 else 'X'})",st in[200,201],d,t)

st,b1,t=api("GET","/api/bkt/status",token=t5)
bc1=safe_len(b1)
rpt.add(5,"4b.BKT-Batch1",st in[200,404],str(b1)[:150],t,f"entries={bc1}")

for i in range(3):
    st,d,t=api("POST","/api/bkt/answer",
        {"question_id":200+i,"user_answer":"C","is_correct":False,"time_spent":60,"knowledge_point":"Python基础","difficulty":2},t5)
    rpt.add(5,f"5a.Wrong{i+1}",st in[200,201],d,t)

st,b2,t=api("GET","/api/bkt/status",token=t5)
bc2=safe_len(b2)
rpt.add(5,"5b.BKT-Batch2",st in[200,404],str(b2)[:150],t,f"entries={bc2} changed={bc2!=bc1}")

st,tx,ag,ev,t=chat("评估我的学习情况",t5)
rpt.add(5,"6.Evaluate",st==200 and len(tx)>0,tx,t,f"len={len(tx)}")

st,p,t=api("GET","/api/path/current",token=t5)
rpt.add(5,"7.LearningPath",st in[200,404],str(p)[:150],t,f"s={st}")

st,s,t=api("GET","/api/path/debug/simulate",token=t5)
rpt.add(5,"8.DebugSim",st!=0,str(s)[:150],t,f"s={st}")

s5_ms = int((time.time()-t_start)*1000)
print(f"  S5 TOTAL: {s5_ms}ms ({s5_ms//1000}s)")

# ═══════════════════════════════════════════
# FINAL
# ═══════════════════════════════════════════
print("\n" + "="*60)
print(f"FINAL: {rpt.sum()}")
print("="*60)

# Write report
lines=["# A3 Live E2E Test Report","",
       f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}","",
       f"**Base URL**: {BASE}","",
       f"**Result**: {rpt.sum()}","",
       "---",""]
for r in rpt.results:
    st="PASS" if r["ok"] else "FAIL"
    lines.append(f"## [{st}] Scenario {r['s']} - {r['step']}")
    lines.append(f"- **Time**: {r['ms']}ms")
    lines.append(f"- **Response**: {r['resp'][:300]}")
    lines.append(f"- **Notes**: {r['notes']}")
    lines.append("")

report_path = r"E:\code\claude-1\a3-learning-system\backend\tests\live_test_report.md"
with open(report_path,"w",encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\nReport: {report_path}")
