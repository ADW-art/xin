"""诊断 Spark API 连通性"""
import requests, os, sys

# 加载 .env
from pathlib import Path
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))

from app.config import settings

print("=== Spark 配置 ===")
print(f"  APP_ID: {settings.spark_app_id}")
print(f"  API_KEY: {settings.spark_api_key[:10]}...")
print(f"  API_SECRET: {settings.spark_api_secret[:10]}...")
print(f"  APP_PASSWORD: {getattr(settings, 'spark_app_password', 'NOT SET')[:10] if getattr(settings, 'spark_app_password', '') else 'NOT SET'}...")
print(f"  BASE_URL: https://spark-api-open.xf-yun.com/v1")
print()

print("=== 1. DNS 解析 ===")
import socket
try:
    ip = socket.gethostbyname("spark-api-open.xf-yun.com")
    print(f"  DNS OK: {ip}")
except Exception as e:
    print(f"  DNS FAIL: {e}")

print("\n=== 2. TCP 连接测试 ===")
try:
    sock = socket.create_connection(("spark-api-open.xf-yun.com", 443), timeout=10)
    print(f"  TCP OK: connected to spark-api-open.xf-yun.com:443")
    sock.close()
except Exception as e:
    print(f"  TCP FAIL: {e}")

print("\n=== 3. HTTP GET 测试 ===")
try:
    token = settings.spark_app_password or settings.spark_api_secret
    r = requests.get(
        "https://spark-api-open.xf-yun.com/v1/models",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    print(f"  HTTP Status: {r.status_code}")
    print(f"  Response: {r.text[:300]}")
except requests.exceptions.ProxyError as e:
    print(f"  PROXY ERROR: {e}")
except requests.exceptions.ConnectionError as e:
    print(f"  CONNECTION ERROR: {e}")
except Exception as e:
    print(f"  ERROR ({type(e).__name__}): {e}")

print("\n=== 4. Chat Completions 测试 ===")
try:
    from app.services.spark_client import SparkClient
    client = SparkClient(
        app_id=settings.spark_app_id,
        api_key=settings.spark_api_key,
        api_secret=settings.spark_api_secret,
        app_password=settings.spark_app_password,
    )
    result = client.chat_sync([
        {"role": "user", "content": "说'你好'"}
    ], temperature=0.3, max_tokens=20)
    print(f"  LLM OK: {result[:100]}")
except Exception as e:
    print(f"  LLM FAIL ({type(e).__name__}): {e}")

print("\n=== 5. 环境变量检查 ===")
for key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "NO_PROXY"]:
    val = os.environ.get(key, "(未设置)")
    if val != "(未设置)":
        print(f"  {key}={val}")
    # 不打印未设置的，保持输出干净
if not any(os.environ.get(k) for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]):
    print("  (无代理环境变量)")
