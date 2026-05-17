"""
讯飞星火 API 连通性测试脚本
运行: python test_spark.py
"""
import json
import ssl
import time
import hmac
import hashlib
import base64
from datetime import datetime
from urllib.parse import urlencode
import websocket
from dotenv import load_dotenv
import os

load_dotenv()

APP_ID = os.getenv("SPARK_APP_ID")
API_KEY = os.getenv("SPARK_API_KEY")
API_SECRET = os.getenv("SPARK_API_SECRET")

# Spark X 版本
VERSIONS = [
    ("wss://spark-api.xf-yun.com/x2", "spark-x"),
    ("wss://spark-api.xf-yun.com/v1/x1", "x1"),
]


def get_auth_url(spark_url):
    """生成带 HMAC-SHA256 签名的 WebSocket URL"""
    # 从URL中提取host和path
    # spark_url 格式: wss://host/path
    url_part = spark_url.replace("wss://", "")
    host = url_part.split("/")[0]
    path = "/" + "/".join(url_part.split("/")[1:])
    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    # 拼签名原文
    signature_origin = f"host: {host}\ndate: {now}\nGET {path} HTTP/1.1"

    # HMAC-SHA256 签名
    signature = base64.b64encode(
        hmac.new(
            API_SECRET.encode(),
            signature_origin.encode(),
            hashlib.sha256,
        ).digest()
    ).decode()

    # 拼 authorization 参数
    authorization_origin = (
        f'api_key="{API_KEY}", '
        f'algorithm="hmac-sha256", '
        f'headers="host date request-line", '
        f'signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode()).decode()

    params = {
        "authorization": authorization,
        "date": now,
        "host": host,
    }
    return f"{spark_url}?{urlencode(params)}"


def try_version(spark_url, domain):
    """尝试用指定版本连接"""
    url = get_auth_url(spark_url)

    ws = websocket.create_connection(url, sslopt={"cert_reqs": ssl.CERT_NONE})

    request = {
        "header": {
            "app_id": APP_ID,
            "uid": "test_user",
        },
        "parameter": {
            "chat": {
                "domain": domain,
                "temperature": 0.7,
                "max_tokens": 1024,
            }
        },
        "payload": {
            "message": {
                "text": [
                    {"role": "user", "content": "你好，请用一句话介绍你自己"}
                ]
            }
        },
    }

    ws.send(json.dumps(request))

    full_content = ""
    full_reasoning = ""
    while True:
        raw = ws.recv()
        response = json.loads(raw)
        code = response["header"]["code"]
        if code != 0:
            ws.close()
            return False, response["header"]["message"]

        choices = response["payload"]["choices"]
        status = choices["status"]
        texts = choices["text"]

        for t in texts:
            if "content" in t:
                full_content += t["content"]
            if "reasoning_content" in t:
                full_reasoning += t["reasoning_content"]

        if status == 2:  # 全部结束
            break

    ws.close()
    result = full_content or full_reasoning or "(empty)"
    return True, result[:200]


def test():
    print("=" * 50)
    print("Xunfei Spark API Test")
    print(f"APP_ID: {APP_ID}")
    print("=" * 50)

    for spark_url, domain in VERSIONS:
        print(f"\nTrying: {domain} ... ", end="", flush=True)
        try:
            ok, msg = try_version(spark_url, domain)
            if ok:
                print(f"SUCCESS!")
                print(f"   Reply: {msg[:100]}...")
                return
            else:
                print(f"FAILED ({msg})")
        except Exception as e:
            print(f"ERROR ({e})")

    print("\n" + "=" * 50)
    print("All versions failed.")
    print("Please check:")
    print("1. Go to https://console.xfyun.cn/")
    print("2. Find your app -> Service Settings")
    print("3. Enable 'Spark Cognitive Model' service for this app")


if __name__ == "__main__":
    test()
