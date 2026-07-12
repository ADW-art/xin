"""
Mermaid 图表渲染服务

通过 mermaid.ink API 将 Mermaid 代码渲染为 PNG/SVG。
mermaid.ink 是官方推荐的在线渲染服务 (https://mermaid.ink)。

用法:
    from app.services.mermaid_service import render_mermaid

    png_bytes = await render_mermaid(mermaid_code, format="png")
    svg_text = await render_mermaid(mermaid_code, format="svg")
"""

import base64
import json
import logging
import zlib
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

MERMAID_INK_BASE = "https://mermaid.ink"


def _encode_mermaid(code: str) -> str:
    """Encode Mermaid code for mermaid.ink URL.

    Uses the pako (zlib) encoding scheme: deflate → base64url.
    """
    # mermaid.ink uses a specific encoding: JSON string → deflate → base64url
    payload = json.dumps({"code": code})
    compressed = zlib.compress(payload.encode("utf-8"), level=9)
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    return encoded


async def render_mermaid(code: str, format: str = "png") -> bytes | str | None:
    """Render Mermaid code to PNG bytes or SVG string using mermaid.ink.

    Args:
        code: Mermaid diagram source code
        format: "png" or "svg"

    Returns:
        PNG bytes (format="png") or SVG string (format="svg"), or None on failure
    """
    try:
        pako_encoded = _encode_mermaid(code)

        if format == "svg":
            url = f"{MERMAID_INK_BASE}/svg/{pako_encoded}"
        else:
            url = f"{MERMAID_INK_BASE}/img/{pako_encoded}?type=png"

        logger.info("MermaidService: requesting render (format=%s, code_len=%d)", format, len(code))

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            if format == "svg":
                return resp.text
            else:
                return resp.content

    except Exception as e:
        logger.warning("MermaidService: render failed (format=%s): %s", format, e)
        return None


def encode_mermaid_for_frontend(code: str) -> str:
    """Generate a mermaid.ink URL that the frontend can embed directly.

    Returns a URL like: https://mermaid.ink/img/pako:<encoded>
    """
    pako_encoded = _encode_mermaid(code)
    return f"{MERMAID_INK_BASE}/img/pako:{pako_encoded}"


def encode_mermaid_svg_url(code: str) -> str:
    """Generate a mermaid.ink SVG URL for frontend embedding."""
    pako_encoded = _encode_mermaid(code)
    return f"{MERMAID_INK_BASE}/svg/pako:{pako_encoded}"
