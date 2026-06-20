"""TTS 语音合成 API"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.tts_service import synthesize_speech
from app.api.auth import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tts", tags=["TTS语音合成"])


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500, description="要合成的文本")
    voice: str = Field(default="xiaoyan", description="发音人: xiaoyan/xiaoyu/xiaofeng/xiaojing")


@router.post("/synthesize")
def tts_synthesize(body: TTSRequest, current_user: User = Depends(get_current_user)):
    """文本转语音 — 返回 MP3 音频"""
    audio = synthesize_speech(body.text, voice=body.voice)
    if audio is None:
        raise HTTPException(status_code=503, detail="语音合成服务暂不可用")
    return Response(content=audio, media_type="audio/mpeg")
