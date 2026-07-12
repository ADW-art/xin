"""
Spark Image Generation Service — 星火图像生成 API

Endpoint: https://spark-api.cn-huabei-1.xf-yun.com/v2.1/tti
Auth: Bearer token (same as Spark text API: APPPassword)
Model: general (通用文生图)

Verified: 2026-07-11 — generates 467KB PNG images from Chinese prompts.
"""
import asyncio
import base64
import logging
import uuid

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

TTI_URL = "https://spark-api.cn-huabei-1.xf-yun.com/v2.1/tti"
TTI_DOMAIN = "general"
VALID_SIZES = {(1024, 1024), (768, 768), (512, 512), (1280, 720), (720, 1280)}

IMAGE_STYLES = {
    "educational": "扁平化教育插图风格，蓝白配色，清晰线条，适合教学场景，简洁明了的信息图表",
    "realistic": "写实风格，高清照片级画质，自然光影，细节丰富",
    "handdrawn": "手绘风格，温暖自然笔触，水彩质感，适合创意教学",
    "infographic": "信息图风格，数据可视化设计，图表元素，现代简约排版",
    "cartoon": "卡通插画风格，可爱生动，色彩明亮，适合低龄学习者",
}

DEFAULT_STYLE = "educational"

MAX_RETRIES = 2
RETRY_DELAY_BASE = 2.0  # seconds, exponential: 2s, 4s


def build_prompt(prompt: str, style: str | None = None) -> str:
    """Append style modifier keywords to prompt."""
    s = style or DEFAULT_STYLE
    style_text = IMAGE_STYLES.get(s, IMAGE_STYLES[DEFAULT_STYLE])
    return f"{prompt}。{style_text}"


def _is_retryable(status: str) -> bool:
    """Check if the error status is retryable (network/timeout, not content filter or param error)."""
    non_retryable = ("content_filtered", "error: 参数格式错误")
    return not any(n in status for n in non_retryable) and status != "success"


async def generate_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    negative_prompt: str = "",
    style: str | None = None,
) -> tuple[str | None, str]:
    """Generate an image from text prompt using Spark image API.

    Args:
        prompt: Chinese/English prompt, max 1024 chars
        width, height: Must be a valid pair from VALID_SIZES
        negative_prompt: What to avoid in the image (optional)
        style: One of IMAGE_STYLES keys, appended to prompt

    Returns:
        (base64_png_data | None, status_str)
    """
    if not settings.spark_app_id or not settings.spark_app_password:
        return None, "error: 图像生成 API 未配置"

    if (width, height) not in VALID_SIZES:
        width, height = 1024, 1024

    full_prompt = build_prompt(prompt, style)

    body = {
        "header": {
            "app_id": settings.spark_app_id,
            "uid": str(uuid.uuid4().hex)[:32],
        },
        "parameter": {
            "chat": {
                "domain": TTI_DOMAIN,
                "width": width,
                "height": height,
            }
        },
        "payload": {
            "message": {
                "text": [{"role": "user", "content": full_prompt[:1024]}]
            },
        },
    }
    if negative_prompt:
        body["payload"]["negative_prompts"] = {"text": negative_prompt[:1024]}

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.spark_app_password}",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                TTI_URL, json=body, headers=headers,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                text = await resp.text()
                if not text or not text.startswith("{"):
                    logger.error("Spark image API: non-JSON (status=%d): %.200s", resp.status, text)
                    return None, f"error: HTTP {resp.status}"

                import json
                result = json.loads(text)
                code = result.get("header", {}).get("code", -1)

                if code == 0:
                    choices = result.get("payload", {}).get("choices", {})
                    text_list = choices.get("text", [])
                    if text_list and text_list[0].get("content"):
                        b64 = text_list[0]["content"]
                        logger.info("Spark image: %dx%d, %d chars base64", width, height, len(b64))
                        return b64, "success"
                    return None, "error: 空响应"
                elif code in (10021, 10022):
                    return None, "content_filtered"
                elif code == 10004:
                    return None, "error: 参数格式错误，请检查请求体"
                else:
                    msg = result.get("header", {}).get("message", f"code={code}")
                    logger.error("Spark image API error (code=%d): %s", code, msg)
                    return None, f"error({code}): {msg}"

    except asyncio.TimeoutError:
        return None, "error: 图像生成超时"
    except Exception as e:
        logger.error("Spark image API exception: %s", e)
        return None, f"error: {str(e)}"


async def generate_and_save(
    prompt: str,
    output_dir: str,
    filename: str | None = None,
    width: int = 1024,
    height: int = 1024,
    style: str | None = None,
    retry: bool = True,
) -> tuple[str | None, str]:
    """Generate image and save to file. Returns (file_path, status).

    Args:
        retry: If True, retry up to MAX_RETRIES times on transient failures.
    """
    import os

    img_base64, status = await generate_image(prompt, width, height, style=style)

    # Retry on transient failures
    if retry and img_base64 is None and _is_retryable(status):
        for attempt in range(1, MAX_RETRIES + 1):
            delay = RETRY_DELAY_BASE ** attempt
            logger.info("Image retry %d/%d after %.1fs (status=%s)", attempt, MAX_RETRIES, delay, status)
            await asyncio.sleep(delay)
            img_base64, status = await generate_image(prompt, width, height, style=style)
            if img_base64 is not None and status == "success":
                break

    if img_base64 is None or status != "success":
        return None, status

    os.makedirs(output_dir, exist_ok=True)
    fname = filename or f"{uuid.uuid4().hex}.png"
    filepath = os.path.join(output_dir, fname)

    with open(filepath, "wb") as f:
        f.write(base64.b64decode(img_base64))

    logger.info("Spark image saved: %s", filepath)
    return filepath, "success"


async def generate_and_save_batch(
    prompts: list[dict],
    output_dir: str,
    resource_id: int,
    retry: bool = True,
) -> list[dict]:
    """Generate multiple images and return result list.

    Args:
        prompts: [{"prompt": str, "style": str|None}, ...]
        output_dir: Directory to save images
        resource_id: Resource ID for filename prefix
        retry: Enable retry on transient failures

    Returns:
        [{"index": i, "url": str, "prompt": str, "status": str}, ...]
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    results = []

    for i, item in enumerate(prompts[:5]):
        prompt_text = item["prompt"].strip()[:900]
        style = item.get("style")
        fname = f"res_{resource_id}_{i}.png"
        filepath, status = await generate_and_save(
            prompt_text, output_dir, fname,
            style=style, retry=retry,
        )
        if filepath:
            url = f"/static/images/{fname}"
            results.append({"index": i, "url": url, "prompt": prompt_text[:100], "status": "success"})
        else:
            results.append({"index": i, "prompt": prompt_text[:100], "status": status})

    return results


def index_images_to_chromadb(
    image_results: list[dict],
    knowledge_points: str,
    resource_id: int,
) -> int:
    """Index generated image prompts into ChromaDB for RAG retrieval.

    Uses BGE-M3 embeddings to vectorize the prompt text, enabling
    cross-modal search: text query → relevant generated images.

    Args:
        image_results: Results from generate_and_save_batch
        knowledge_points: Comma-separated knowledge point tags
        resource_id: Resource ID for linking

    Returns:
        Number of images indexed
    """
    try:
        from app.services.rag_service import _embed, is_rag_ready
        if not is_rag_ready():
            logger.info("Image indexing skipped: RAG not ready")
            return 0

        documents = []
        metadatas = []
        ids = []
        for img in image_results:
            if img["status"] != "success":
                continue
            doc_text = f"{knowledge_points} — {img['prompt']}"
            documents.append(doc_text)
            metadatas.append({
                "source": "image_generation",
                "resource_id": resource_id,
                "knowledge_points": knowledge_points,
                "image_url": img["url"],
                "prompt": img["prompt"],
            })
            ids.append(f"img_res_{resource_id}_{img['index']}")

        if not documents:
            return 0

        embeddings = _embed(documents)
        if not embeddings or len(embeddings) != len(documents):
            logger.warning("Image indexing: embedding failed")
            return 0

        from app.core.chroma_client import add_to_collection
        add_to_collection(
            name="image_index",
            documents=documents,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings,
        )
        logger.info("Image indexing: %d images → ChromaDB 'image_index'", len(documents))
        return len(documents)
    except Exception as e:
        logger.warning("Image indexing failed (non-blocking): %s", e)
        return 0
