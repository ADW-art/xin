"""
讯飞语音合成 (TTS) — WebSocket流式版

API: wss://tts-api.xfyun.cn/v2/tts
鉴权: HMAC-SHA256 签名 (与星火对话相同模式)
"""
import hashlib
import hmac
import base64
import json
import logging
import ssl
import time
from datetime import datetime
from urllib.parse import urlencode
import websocket

import re

from app.config import settings

logger = logging.getLogger(__name__)

TTS_URL = "wss://tts-api.xfyun.cn/v2/tts"
TTS_HOST = "tts-api.xfyun.cn"

# Markdown 清洗正则 (TTS 朗读前移除格式标记)
_MD_CLEAN_PATTERNS = [
    (re.compile(r'#{1,6}\s+'), ''),           # 标题
    (re.compile(r'\*\*(.+?)\*\*'), r'\1'),     # 粗体
    (re.compile(r'\*(.+?)\*'), r'\1'),         # 斜体
    (re.compile(r'`{1,3}[^`]*`{1,3}'), ''),   # 代码
    (re.compile(r'\|[^|]*\|'), ''),            # 表格行
    (re.compile(r'---+'), ''),                 # 分隔线
    (re.compile(r'\[([^\]]+)\]\([^)]+\)'), r'\1'),  # 链接
    (re.compile(r'^>\s+', re.MULTILINE), ''),  # 引用
    (re.compile(r'^[\s]*[-*+]\s+', re.MULTILINE), ''),  # 列表
]


def _clean_markdown(text: str) -> str:
    """移除 Markdown 格式标记，保留纯文本供 TTS 朗读"""
    for pattern, replacement in _MD_CLEAN_PATTERNS:
        text = pattern.sub(replacement, text)
    # 压缩多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _get_tts_auth_url() -> str:
    """构建带鉴权的 WebSocket URL"""
    api_key = settings.tts_api_key or settings.spark_api_key
    api_secret = settings.tts_api_secret or settings.spark_api_secret
    host = TTS_HOST
    path = "/v2/tts"
    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    signature_origin = f"host: {host}\ndate: {now}\nGET {path} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(api_secret.encode(), signature_origin.encode(), hashlib.sha256).digest()
    ).decode()
    authorization = base64.b64encode(
        f'api_key="{api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature}"'.encode()
    ).decode()
    params = {"authorization": authorization, "date": now, "host": host}
    return f"{TTS_URL}?{urlencode(params)}"


def synthesize_speech(text: str, voice: str = "xiaoyan", speed: int = 50) -> bytes | None:
    """将文本转为语音，返回 MP3 音频字节

    Args:
        text: 要合成的文本 (最大 500 字)
        voice: 发音人 xiaoyan/xiaoyu/xiaofeng/xiaomei/xiaojing
        speed: 语速 0-100
    """
    if not text:
        return None

    # 清洗 Markdown 格式标记，保留纯文本供朗读
    text = _clean_markdown(text)
    if len(text) > 500:
        text = text[:500]

    app_id = settings.tts_app_id or settings.spark_app_id
    if not app_id:
        logger.warning("TTS: 未配置 APP_ID")
        return None

    url = _get_tts_auth_url()
    ws = None
    audio_chunks = []

    try:
        ws = websocket.create_connection(url, timeout=8)

        request = {
            "common": {"app_id": app_id},
            "business": {
                "vcn": voice,
                "speed": speed,
                "volume": 50,
                "pitch": 50,
                "tte": "UTF8",
                "aue": "lame",  # MP3
            },
            "data": {
                "status": 2,  # 2 = 一次性传输全部文本
                "text": base64.b64encode(text.encode("utf-8")).decode(),
            },
        }
        ws.send(json.dumps(request))

        while True:
            response = ws.recv()
            if isinstance(response, bytes):
                audio_chunks.append(response)
            else:
                data = json.loads(response)
                code = data.get("code", -1)
                if code != 0:
                    logger.warning("TTS: 错误 code=%s msg=%s", code, data.get("message", ""))
                    break
                status = data.get("data", {}).get("status", 1)
                audio_b64 = data.get("data", {}).get("audio", "")
                if audio_b64:
                    try:
                        audio_chunks.append(base64.b64decode(audio_b64))
                    except Exception:
                        pass
                if status == 2:  # 结束
                    break
        ws.close()
        ws = None

        if audio_chunks:
            return b"".join(audio_chunks)
        return None

    except Exception as e:
        logger.warning("TTS: WebSocket失败 %s", e)
        return None
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
