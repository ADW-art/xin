"""
SeeDance Video Generation Service — 火山引擎视频生成 API

SeeDance 2.0 (ByteDance/Volcengine) — 赛题明确点名的多模态视频生成模型.

Endpoint: https://api.volcengine.com (or https://ark.cn-beijing.volces.com)
Auth: Access Key + Secret Key (需用户在 console.volcengine.com 申请)

Usage:
    from app.services.seedance_service import submit_video, poll_video, generate_video
"""
import asyncio
import logging
import time
import os
import uuid

import aiohttp

logger = logging.getLogger(__name__)

# Will be configured when user provides API key
_SEEDANCE_API_KEY: str | None = None
_SEEDANCE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def configure_seedance(api_key: str, base_url: str | None = None):
    """Configure SeeDance API credentials at runtime."""
    global _SEEDANCE_API_KEY, _SEEDANCE_BASE_URL
    _SEEDANCE_API_KEY = api_key
    if base_url:
        _SEEDANCE_BASE_URL = base_url
    logger.info("SeeDance configured: %s", _SEEDANCE_BASE_URL)


def is_configured() -> bool:
    return _SEEDANCE_API_KEY is not None and len(_SEEDANCE_API_KEY) > 0


async def submit_task(
    prompt: str,
    resolution: str = "720p",
    duration: int = 5,
    aspect_ratio: str = "16:9",
    audio: bool = True,
) -> tuple[str | None, str]:
    """Submit a video generation task.

    Returns (job_id, status) where status is "submitted" or "error: ..."
    """
    if not is_configured():
        return None, "error: SeeDance API 未配置, 请在 console.volcengine.com 申请"

    url = f"{_SEEDANCE_BASE_URL}/video/generation"
    headers = {
        "Authorization": f"Bearer {_SEEDANCE_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "doubao-seedance-1-0-pro-250528",
        "prompt": prompt[:2000],
        "resolution": resolution,
        "duration": min(max(duration, 4), 15),
        "aspect_ratio": aspect_ratio,
        "audio": audio,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                result = await resp.json()
                job_id = result.get("job_id") or result.get("id")
                if job_id:
                    logger.info("SeeDance task submitted: %s", job_id)
                    return job_id, "submitted"
                error_msg = result.get("message", str(result))
                logger.error("SeeDance submit failed: %s", error_msg)
                return None, f"error: {error_msg}"
    except Exception as e:
        return None, f"error: {str(e)}"


async def poll_task(job_id: str) -> dict:
    """Poll a video generation task status.

    Returns {"status": "..."|"error", "video_url": "...", "progress": 0-100}
    """
    if not is_configured():
        return {"status": "error", "message": "SeeDance API 未配置"}

    url = f"{_SEEDANCE_BASE_URL}/video/status/{job_id}"
    headers = {"Authorization": f"Bearer {_SEEDANCE_API_KEY}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                result = await resp.json()
                return {
                    "status": result.get("status", "unknown"),
                    "video_url": result.get("video_url") or result.get("output", {}).get("video_url"),
                    "progress": result.get("progress", 0),
                    "message": result.get("message", ""),
                }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def generate_video(
    prompt: str,
    resolution: str = "720p",
    duration: int = 5,
    aspect_ratio: str = "16:9",
    poll_interval: float = 5.0,
    max_wait: float = 300.0,
) -> tuple[str | None, str]:
    """Submit a video task and wait for completion.

    Returns (video_url, status).
    """
    job_id, status = await submit_task(prompt, resolution, duration, aspect_ratio)
    if not job_id:
        return None, status

    elapsed = 0.0
    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        result = await poll_task(job_id)
        if result["status"] == "completed":
            return result.get("video_url"), "completed"
        if result["status"] in ("failed", "error"):
            return None, f"error: {result.get('message', '生成失败')}"
        logger.info("SeeDance job %s progress: %d%%", job_id, result.get("progress", 0))

    return None, f"error: 超时 ({max_wait}s)"
