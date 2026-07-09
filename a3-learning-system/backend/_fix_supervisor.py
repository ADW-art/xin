fp = r"e:\code\claude-1\a3-learning-system\backend\app\agents\supervisor.py"
c = open(fp, "r", encoding="utf-8").read()
om = "# resource:  
im = ""# chat: system questions
if any(k in text for k in ["\u4ecc\u7261\u1d89\u4e39\u20320", "\u4e0d\u768c\u5211\u805a", "\u4e0d%Å5058\u5a0a\u4e8e", "what can you do", "who are you"]):
    return {"intent": "chat", "params": {}}

# resource: 
if om in c:
    c = c.replace(om, nm, 1)
open(fp, "w", encoding="utf-8").write(c)
print("OK")