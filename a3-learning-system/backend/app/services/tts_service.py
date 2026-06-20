"""
讯飞语音合成 (TTS) 服务 — 将教学文本转为语音

API: 讯飞在线语音合成 HTTP 接口
文档: https://www.xfyun.cn/doc/tts/online_tts/API.html
"""
import hashlib
import base64
import json
import logging
import time
import requests

from app.config import settings

logger = logging.getLogger(__name__)

TTS_URL = "https://api.xfyun.cn/v1/service/v1/tts"


def synthesize_speech(text: str, voice: str = "xiaoyan", speed: int = 50) -> bytes | None:
    """将文本转为语音，返回 MP3 音频字节

    Args:
        text: 要合成的文本 (最大 500 字)
        voice: 发音人 (xiaoyan/xiaoyu/xiaofeng/xiaojing/xiaomei)
        speed: 语速 0-100, 50为正常
    """
    if not text or len(text) > 500:
        text = text[:500]
    if not settings.spark_api_key or not settings.spark_api_secret:
        logger.warning("TTS: 未配置 API Key，跳过语音合成")
        return None

    # 构图 X-Param
    param_data = {
        "auf": "audio/L16;rate=16000",
        "aue": "lame",
        "voice_name": voice,
        "speed": str(speed),
        "volume": "50",
        "pitch": "50",
        "engine_type": "intp65",
        "text_type": "text",
    }
    x_param = base64.b64encode(json.dumps(param_data).encode()).decode()
    x_cur_time = str(int(time.time()))
    x_check_sum = hashlib.md5(
        f"{settings.spark_api_key}{x_cur_time}{x_param}".encode()
    ).hexdigest()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "X-Param": x_param,
        "X-CurTime": x_cur_time,
        "X-CheckSum": x_check_sum,
        "X-Appid": settings.spark_app_id,
        "X-Real-Ip": "127.0.0.1",
    }

    try:
        resp = requests.post(
            TTS_URL,
            headers=headers,
            data=f"text={text}".encode("utf-8"),
            timeout=10,
        )
        if resp.status_code == 200:
            content_type = resp.headers.get("Content-Type", "")
            if "audio" in content_type or len(resp.content) > 100:
                return resp.content  # MP3 binary
            try:
                result = resp.json()
                code = result.get("code", "")
                if code == "0":
                    audio_b64 = result.get("data", {}).get("audio", "")
                    if audio_b64:
                        return base64.b64decode(audio_b64)
                logger.warning("TTS: API返回 code=%s desc=%s", code, result.get("desc", ""))
            except Exception:
                logger.warning("TTS: 响应解析失败 len=%d", len(resp.content))
            return None
        else:
            logger.warning("TTS: HTTP %d %s", resp.status_code, resp.text[:100])
            return None
    except Exception as e:
        logger.warning("TTS: 请求失败 %s", e)
        return None
