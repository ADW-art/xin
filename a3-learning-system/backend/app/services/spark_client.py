"""
讯飞星火大模型客户端（OpenAI 兼容协议版）

适配 Spark Lite / Pro / Max / 4.0Ultra，使用 OpenAI 兼容的 REST API。
对外暴露 chat_stream() 和 chat_sync()，上层 Agent 不感知底层协议。

接口地址: https://spark-api-open.xf-yun.com/v1/chat/completions
认证方式: Bearer {APPPassword}
模型名:   lite / pro / max / 4.0Ultra

使用方式:
    spark = SparkClient(app_id, api_key, api_secret, app_password)

    # 流式（逐 token 返回，用于 SSE 推送给前端）
    for chunk in spark.chat_stream([{"role": "user", "content": "你好"}]):
        print(chunk, end="", flush=True)

    # 同步（等全部生成完一次返回）
    result = spark.chat_sync([{"role": "user", "content": "1+1=?"}])

多模态支持（OpenAI Vision API 格式）：
  messages 支持两种格式：
    1. 纯文本:   {"role": "user", "content": "你好"}
    2. 图片+文本: {"role": "user", "content": [
         {"type": "text", "text": "描述这张图"},
         {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
       ]}
"""

import json
import logging
import os
from typing import Generator, Union

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# v3: 可重试异常类型 — 网络/超时可重试, 认证/参数错误不可重试
# Reserved for future custom retry logic (SparkRateLimitError, SparkNetworkError, SparkAuthError)
class SparkAPIError(Exception): pass
class SparkAuthError(SparkAPIError): pass
class SparkRateLimitError(SparkAPIError): pass
class SparkNetworkError(SparkAPIError): pass

API_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
    reraise=True,
)

# 默认使用 4.0Ultra（最新最强模型），可通过 SPARK_MODEL 环境变量覆盖
DEFAULT_MODEL = os.getenv("SPARK_MODEL", "4.0Ultra")


class SparkClient:
    """讯飞星火客户端（OpenAI 兼容 HTTP 协议）

    默认使用 4.0Ultra 模型（最新最强）。
    设置环境变量 SPARK_MODEL=pro / max / lite 可切换模型。
    """

    BASE_URL = "https://spark-api-open.xf-yun.com/v1"

    def __init__(self, app_id: str, api_key: str, api_secret: str, app_password: str = "", model: str = ""):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.model = model or DEFAULT_MODEL
        # HTTP 接口使用 APPPassword 作为 Bearer Token
        self._token = app_password or api_secret
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }
        # TLS 验证：默认启用，仅 DEBUG_SKIP_TLS=1 时跳过
        # 连接策略：禁用系统代理直连（讯飞API需绕过企业代理）
        self._session = requests.Session()
        self._session.trust_env = False
        self._session.proxies = {'http': None, 'https': None}
        if os.getenv("DEBUG_SKIP_TLS") == "1":
            self._session.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.warning("TLS验证已禁用（DEBUG_SKIP_TLS=1），仅限开发环境！")

    @API_RETRY
    def chat_sync(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """同步对话，等全部生成完毕后返回完整文本 (v3: 3次指数退避重试)"""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            resp = self._session.post(
                f"{self.BASE_URL}/chat/completions",
                headers=self._headers,
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()

            # 检测 API 级错误 (code != 0, 且 response 中有 error/message 字段)
            code = data.get("code", 0)
            if code != 0:
                msg = data.get("message", data.get("error", {}).get("message", str(data)))
                raise RuntimeError(f"Spark API 错误 (code={code}): {msg}")

            return data["choices"][0]["message"]["content"]

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"请求失败: {e}") from e

    @API_RETRY
    def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        """流式对话，逐段返回大模型生成的内容 (v3: 3次指数退避重试)"""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            resp = self._session.post(
                f"{self.BASE_URL}/chat/completions",
                headers=self._headers,
                json=payload,
                timeout=60,
                stream=True,
            )
            resp.raise_for_status()

            yielded_any = False
            first_line = True
            # 强制 UTF-8 解码，避免 iter_lines 自动编码检测错误导致中文乱码
            for line in resp.iter_lines():
                if not line:
                    continue
                # 手动 UTF-8 解码
                try:
                    text = line.decode("utf-8")
                except UnicodeDecodeError:
                    text = line.decode("latin-1")  # 兜底

                if first_line:
                    first_line = False
                    logger.debug("Spark stream first line: %s", text[:200])

                if not text.startswith("data: "):
                    # 非流式错误响应 (API 直接返回 JSON 错误)
                    if not text.startswith("data:") and text.strip().startswith("{"):
                        try:
                            err = json.loads(text.strip())
                        except json.JSONDecodeError:
                            logger.warning("Spark: 无法解析响应首行: %s", text[:200])
                            continue
                        code = err.get("code", "unknown")
                        msg = err.get("message", err.get("error", {}).get("message", str(err)))
                        logger.error("Spark API 错误 (model=%s, code=%s): %s", self.model, code, msg)
                        raise RuntimeError(f"Spark API 错误 (code={code}): {msg}")
                    continue

                data_str = text[6:]
                if data_str.strip() == "[DONE]":
                    break

                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # 检测流式行内嵌的 API 错误 (如 AppIdNoAuthError)
                code = chunk.get("code", 0)
                if code != 0:
                    msg = chunk.get("message", str(chunk))
                    logger.error("Spark API 错误 (model=%s, code=%s): %s", self.model, code, msg)
                    raise RuntimeError(f"Spark API 错误 (code={code}): {msg}")

                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yielded_any = True
                        yield content

            if not yielded_any:
                logger.warning("Spark stream: 流式请求返回 200 但未 yield 任何内容 (model=%s)", self.model)

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"流式请求失败: {e}") from e


# ============================================================
# 快速测试
# ============================================================
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    spark = SparkClient(
        app_id=os.getenv("SPARK_APP_ID", ""),
        api_key=os.getenv("SPARK_API_KEY", ""),
        api_secret=os.getenv("SPARK_API_SECRET", ""),
        app_password=os.getenv("SPARK_APP_PASSWORD", ""),
    )

    print("=== 测试 chat_sync ===")
    try:
        result = spark.chat_sync([{"role": "user", "content": "说OK"}], max_tokens=10)
        print(f"结果: [{result}]")
    except Exception as e:
        print(f"错误: {e}")

    print("\n=== 测试 chat_stream ===")
    try:
        for chunk in spark.chat_stream([{"role": "user", "content": "用一句话说你好"}]):
            print(chunk, end="", flush=True)
        print()
    except Exception as e:
        print(f"错误: {e}")
