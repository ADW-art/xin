"""
讯飞星火大模型 WebSocket 客户端

封装了 WebSocket 连接、HMAC-SHA256 签名、流式响应解析。
对外暴露 chat_stream() 和 chat_sync()，上层 Agent 不感知底层协议。

使用方式:
    spark = SparkClient(app_id, api_key, api_secret)

    # 流式（逐 token 返回，用于 SSE 推送给前端）
    for chunk in spark.chat_stream([{"role": "user", "content": "你好"}]):
        print(chunk, end="", flush=True)

    # 同步（等全部生成完一次返回，用于意图分类等需要完整结果的场景）
    result = spark.chat_sync([{"role": "user", "content": "1+1=?"}])
"""

import json
import ssl
import hmac
import hashlib
import base64
from datetime import datetime
from urllib.parse import urlencode
from typing import Generator

import websocket


class SparkClient:
    """讯飞星火 WebSocket 客户端"""

    # 讯飞星火 V4.0 API 地址
    #类属性-公用一块地址
    SPARK_URL = "wss://spark-api.xf-yun.com/v4.0/chat"
    DOMAIN = "4.0Ultra"

    #创建对象时调用-构造函数-传入3个值
    def __init__(self, app_id: str, api_key: str, api_secret: str):
        #实例属性，每个对象不同--把参数存到对象里面
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret

    # ============================================================
    # 私有方法：HMAC 签名
    # ============================================================
    def _get_auth_url(self) -> str:#_开头表示私有
        """生成带 HMAC-SHA256 签名的 WebSocket URL

        每次调用都重新生成，因为签名里包含 UTC 时间戳。
        时间戳变了 → 签名变了 → 防重放攻击
        """
        host = "spark-api.xf-yun.com"
        path = "/v4.0/chat"

        # 1. 获取当前 UTC 时间（讯飞要求 GMT 格式）
        now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

        # 2. 拼签名原文：host + date + request-line
        signature_origin = f"host: {host}\ndate: {now}\nGET {path} HTTP/1.1"

        # 3. HMAC-SHA256 哈希 → Base64
        signature = base64.b64encode(#base64编码
            hmac.new(#密钥-原文-算法->搅拌
                self.api_secret.encode(),#encode字符串转换为字节序列
                signature_origin.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()#变回字符串

        # 4. 拼 authorization 参数字符串
        authorization_origin = (
            f'api_key="{self.api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature}"'#字符串糊糊
        )

        # 5. Base64 编码后拼到 URL 参数里
        authorization = base64.b64encode(
            authorization_origin.encode()
        ).decode()

        params = {
            "authorization": authorization,
            "date": now,
            "host": host,
        }
        return f"{self.SPARK_URL}?{urlencode(params)}"#字典转化为url参数形式

    # ============================================================
    # 公开方法1：流式对话（逐 token 返回）
    # ============================================================
    def chat_stream(
        self,
        messages: list[dict],#多个字典组成的列表
        temperature: float = 0.7,#有默认值，传参调用函数时可以显示指定/不写
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:#Generator可以多次返回值(特殊函数)
        """流式对话，逐段返回大模型生成的内容

        Args:
            messages: [{"role":"user","content":"..."}, ...]
            temperature: 0.0=确定性输出, 1.0=更多随机性
            max_tokens: 本次最多生成的 token 数

        Yields:
            str: 每次产出一小段文本（可能 1~5 个字）
        """
        # 步骤1：获取鉴权 URL
        url = self._get_auth_url()

        # 步骤2：建立 WebSocket 连接
        ws = websocket.create_connection(
            url,
            sslopt={"cert_reqs": ssl.CERT_NONE},
        )

        # 步骤3：按讯飞要求的格式构造请求体
        request_body = {
            "header": {
                "app_id": self.app_id,
                "uid": "user_001",  # 后续会从 Agent State 传入真实用户 ID
            },
            "parameter": {
                "chat": {
                    "domain": self.DOMAIN,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
            },
            "payload": {
                "message": {
                    "text": messages
                }
            },
        }

        # 步骤4：发送请求
        ws.send(json.dumps(request_body))#python字典->json格式长字符串

        # 步骤5：循环接收流式响应
        while True:
            # recv() 阻塞等待下一个数据帧
            response = json.loads(ws.recv())#recv接收信息-阻塞函数

            # 检查错误码
            code = response["header"]["code"]
            if code != 0:
                error_msg = response["header"].get("message", "未知错误")
                ws.close()
                raise RuntimeError(
                    f"讯飞 API 错误 (code={code}): {error_msg}"
                )

            # 提取文本内容
            payload = response["payload"]
            choices = payload["choices"]
            status = choices["status"]       # 0=首帧, 1=中间帧, 2=尾帧
            texts = choices.get("text", [])

            # 把这帧的文字内容 yield 出去
            for t in texts:
                content = t.get("content", "")
                if content:
                    yield content #yield逐字返回

            # status == 2 表示最后一段，退出循环
            if status == 2:
                break

        # 步骤6：关闭连接
        ws.close()

    # ============================================================
    # 公开方法2：同步对话（等全部生成完一次返回）
    # ============================================================
    def chat_sync(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """同步对话，等全部生成完毕后返回完整文本

        内部调用 chat_stream()，把所有 chunk 拼接后返回。
        用于需要完整结果的场景（如 Supervisor 意图分类）。
        """
        full_text = ""
        for chunk in self.chat_stream(messages, temperature, max_tokens):
            full_text += chunk#拼接
        return full_text


# ============================================================
# 快速测试（直接运行本文件时执行）
# ============================================================
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    # 读 .env 中的凭证
    load_dotenv()

    spark = SparkClient(
        app_id=os.getenv("SPARK_APP_ID", ""),#获取环境变量读数据
        api_key=os.getenv("SPARK_API_KEY", ""),
        api_secret=os.getenv("SPARK_API_SECRET", ""),
    )

    # 测试 chat_sync
    print("=== 测试 chat_sync ===")
    result = spark.chat_sync(
        [{"role": "user", "content": "你好，介绍一下你自己"}]
    )
    print(f"结果: {result[:100]}...\n")#取0-99

    # 测试 chat_stream
    print("=== 测试 chat_stream ===")
    for chunk in spark.chat_stream(
        [{"role": "user", "content": "用一句话介绍 rest"}]
    ):
        print(chunk, end="", flush=True)#换行？-立即显示
    print("\n")
