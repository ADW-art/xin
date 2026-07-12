"""
DeepSeek 大模型客户端（OpenAI 兼容协议）

接口同 SparkClient (chat_sync / chat_stream)，上层 Agent 无感知切换。

接口地址: https://api.deepseek.com/v1/chat/completions
认证方式: Bearer {api_key}
模型:     deepseek-chat / deepseek-reasoner
"""

import json
import logging
import os
from typing import Generator

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
BASE_URL = "https://api.deepseek.com/v1"

API_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
    reraise=True,
)


class DeepSeekClient:
    """DeepSeek 客户端（OpenAI 兼容 HTTP 协议）

    默认使用 deepseek-chat 模型。
    设置环境变量 DEEPSEEK_MODEL=deepseek-reasoner 可切换到 R1。
    """

    def __init__(self, api_key: str = "", model: str = "", base_url: str = ""):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self._base_url = base_url or BASE_URL
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
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
        """同步对话，等全部生成完毕后返回完整文本"""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            resp = self._session.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers,
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            code = data.get("code", 0)
            if code != 0:
                msg = data.get("message", data.get("error", {}).get("message", str(data)))
                raise RuntimeError(f"DeepSeek API 错误 (code={code}): {msg}")

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
        """流式对话，逐段返回大模型生成的内容"""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            resp = self._session.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers,
                json=payload,
                timeout=120,
                stream=True,
            )
            resp.raise_for_status()

            yielded_any = False
            first_line = True
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    text = line.decode("utf-8")
                except UnicodeDecodeError:
                    text = line.decode("latin-1")

                if first_line:
                    first_line = False
                    logger.debug("DeepSeek stream first line: %s", text[:200])

                if not text.startswith("data: "):
                    if not text.startswith("data:") and text.strip().startswith("{"):
                        try:
                            err = json.loads(text.strip())
                        except json.JSONDecodeError:
                            logger.warning("DeepSeek: 无法解析响应首行: %s", text[:200])
                            continue
                        code = err.get("code", "unknown")
                        msg = err.get("message", err.get("error", {}).get("message", str(err)))
                        logger.error("DeepSeek API 错误 (model=%s, code=%s): %s", self.model, code, msg)
                        raise RuntimeError(f"DeepSeek API 错误 (code={code}): {msg}")
                    continue

                data_str = text[6:]
                if data_str.strip() == "[DONE]":
                    break

                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                code = chunk.get("code", 0)
                if code != 0:
                    msg = chunk.get("message", str(chunk))
                    logger.error("DeepSeek API 错误 (model=%s, code=%s): %s", self.model, code, msg)
                    raise RuntimeError(f"DeepSeek API 错误 (code={code}): {msg}")

                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yielded_any = True
                        yield content

            if not yielded_any:
                logger.warning("DeepSeek stream: 流式请求返回 %d 但未 yield 任何内容 (model=%s)",
                             resp.status_code, self.model)

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"流式请求失败: {e}") from e
