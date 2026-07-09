fp = r"e:\code\claude-1\a3-learning-system\backend\app\agents\supervisor.py"
c = open(fp, "r", encoding="utf-8").read()
anchor = "\u5e2e\u6211\u5b66\", \u201c\u4ecb\u7ecd\u4e00\u4e0b"
insert = """
    if any(k in text for k in ["\u4ecb\u7ecd\u4e00\u4e0b\u4f60", "\u4f60\u7684\u529f\u80fd", "\u4f60\u80fd\u505a\u4ec0\u4e48", "what can you do", "who are who"]):
        return {"intent": "chat", "params": {}}
`n`n    if any(k in text for k in ["\u6559\u6211\", \u201c\u4ecb\u7ecd\u4e00\u4e0b'
if anchor in c:
    c = c.replace(anchor, insert, 1)
    open(fp, "w", encoding="utf-8").write(c)
    print("OK")
else:
    print("WARN: anchor not found")