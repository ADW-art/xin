"""
讯飞语音合成 (TTS) 服务 — 将教学文本转为语音

API 文档: https://www.xfyun.cn/doc/tts/online_tts/API.html
"""
import hashlib
import hmac
import base64
import json
import logging
import time
from datetime import datetime
from urllib.parse import urlencode
import requests

from app.config import settings

logger = logging.getLogger(__name__)

TTS_URL = "https://tts-api.xfyun.cn/v2/tts"
TTS_HOST = "tts-api.xfyun.cn"


def _build_tts_auth_params() -> dict:
    """构建 TTS API 鉴权参数 (HMAC-SHA256 签名)"""
    api_key = settings.spark_api_key
    api_secret = settings.spark_api_secret

    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    signature_origin = f"host: {TTS_HOST}\ndate: {now}\nPOST /v2/tts HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(api_secret.encode(), signature_origin.encode(), hashlib.sha256).digest()
    ).decode()
    authorization = base64.b64encode(
        f'api_key="{api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature}"'.encode()
    ).decode()

    return {
        "authorization": authorization,
        "date": now,
        "host": TTS_HOST,
    }


def synthesize_speech(text: str, voice: str = "xiaoyan", speed: int = 50) -> bytes | None:
    """将文本转为语音，返回 MP3 音频字节

    Args:
        text: 要合成的文本 (最大 500 字)
        voice: 发音人 (xiaoyan/xiaoyu/xiaofeng/xiaojing)
        speed: 语速 0-100, 50为正常
    """
    if not text or len(text) > 500:
        text = text[:500]
    if not settings.spark_api_key or not settings.spark_api_secret:
        logger.warning("TTS: 未配置 API Key，跳过语音合成")
        return None

    auth_params = _build_tts_auth_params()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "Authorization": f'Bearer {auth_params["authorization"]}',
        "Date": auth_params["date"],
        "Host": auth_params["host"],
    }
    body = {
        "text": text,
        "vcn": voice,
        "speed": speed,
        "volume": 50,
        "pitch": 50,
        "tte": "UTF8",
        "auf": "audio/L16;rate=16000",
        "aue": "lame",
    }
    try:
        resp = requests.post(
            TTS_URL,
            headers=headers,
            data=urlencode(body),
            params=auth_params,
            timeout=10,
        )
        if resp.status_code == 200:
            result = resp.json()
            if result.get("code") == 0 and result.get("data", {}).get("audio"):
                audio_b64 = result["data"]["audio"]
                return base64.b64decode(audio_b64)
            else:
                logger.warning("TTS: API返回错误 code=%s msg=%s", result.get("code"), result.get("message"))
                return None
        else:
            logger.warning("TTS: HTTP %d %s", resp.status_code, resp.text[:100])
            return None
    except Exception as e:
        logger.warning("TTS: 请求失败 %s", e)
        return None
