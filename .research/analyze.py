import re
data = open(r"E:\code\.research\bing_raw.html", "r", encoding="utf-8").read()
# find all http links in href attributes
hrefs = re.findall(r'href="(https?://[^"]+)"', data)
seen = set()
for h in hrefs:
    if h in seen: continue
    seen.add(h)
    b = any(x in h for x in ["bing.com","microsoft.com","live.com"])
    if b: continue
    bad = any(x in h for x in [".js",".css",".png",".svg"])
    if bad: continue
    # find nearby text
    idx = data.find(h)
    snippet = data[max(0,idx-200):idx+len(h)+200]
    # extract any text between tags near this link
    texts = re.findall(r'>([^<]{10,})<', snippet)
    title = texts[0] if texts else "(no title)"
    print(f"[{title.strip()[:80]}]")
    print(h)
    print()
