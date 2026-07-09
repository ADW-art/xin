"""GitHub API 连接器 - 读取 CI 结果、Issues、PRs"""
import requests, warnings, json, sys
warnings.filterwarnings("ignore")

OWNER = "ADW-art"
REPO = "xin"
BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"
H = {"User-Agent": "ADW-art/xin", "Accept": "application/vnd.github.v3+json"}

def get(path):
    r = requests.get(BASE + path, headers=H, timeout=15, verify=False)
    return r.json() if r.status_code == 200 else {"error": r.status_code, "message": r.text[:200]}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(json.dumps(get("/actions/runs?per_page=5"), indent=2)[:1000])
    elif cmd == "issues":
        print(json.dumps(get("/issues?state=open&per_page=10"), indent=2)[:1000])
    elif cmd == "pulls":
        print(json.dumps(get("/pulls?state=open&per_page=10"), indent=2)[:1000])
    elif cmd == "workflows":
        print(json.dumps(get("/actions/workflows"), indent=2)[:1000])
    else:
        print(json.dumps(get(cmd), indent=2)[:1000])
