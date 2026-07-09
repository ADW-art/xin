"""视频生成 API — MP4 教学视频生成与查询"""
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.api.auth import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/video", tags=["视频生成"])

class VideoGenerateRequest(BaseModel):
    script_text: str = Field(..., min_length=10, max_length=10000)
    title: str = Field(default="学习视频", max_length=200)

@router.post("/generate")
async def generate_video(body: VideoGenerateRequest, current_user: User = Depends(get_current_user)):
    from app.services.video_service import gen_mp4
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = await loop.run_in_executor(pool, gen_mp4, body.script_text)
    if result is None:
        raise HTTPException(503, "视频生成服务不可用")
    if result.get("error"):
        raise HTTPException(503, result["error"])
    return result

@router.get("/status")
def video_status():
    import shutil
    return {"ffmpeg_available": shutil.which("ffmpeg") is not None}
