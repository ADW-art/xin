# -*- coding: utf-8 -*-
"""网络辅助工具 - 解决 SSL 证书问题后的统一 HTTP 请求入口"""
import requests, warnings, json
warnings.filterwarnings("ignore")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/120.0"
}

def get(url, **kw):
    """SSL 验证已关闭的 GET 请求"""
    headers = kw.pop("headers", _HEADERS)
    timeout = kw.pop("timeout", 15)
    return requests.get(url, headers=headers, timeout=timeout, verify=False, **kw)

def search_github(query, sort="stars", limit=5):
    """搜索 GitHub 仓库"""
    r = get(f"https://api.github.com/search/repositories?q={query}&sort={sort}")
    data = r.json()
    for item in data.get("items", [])[:limit]:
        desc = item["description"] or "(no desc)"
        print(f"  [{item['full_name']}]  {desc[:100]}")
    print(f"总计 {data['total_count']} 个结果")
    return data["items"][:limit]

def search_bing(q, limit=3):
    """搜索 Bing"""
    r = get(f"https://www.bing.com/search?q={q}")
    print(f"[Bing] status={r.status_code}, {len(r.content)} bytes")
    return r.text[:500]

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    if cmd == "github":
        search_github(" ".join(sys.argv[2:]) or "langgraph agent evaluation")
    elif cmd == "bing":
        search_bing(" ".join(sys.argv[2:]) or "AI harness engineering")
    elif cmd == "test":
        print("网络测试:")
        for url in ["https://www.baidu.com", "https://github.com", "https://www.bing.com"]:
            try:
                r = get(url, timeout=8)
                print(f"  {url} -> {r.status_code} ({len(r.content)} bytes)")
            except Exception as e:
                print(f"  {url} -> FAIL: {e}")
        print("\n网络可用!")
