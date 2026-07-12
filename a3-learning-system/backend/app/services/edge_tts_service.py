"""
Edge TTS Service — Microsoft Edge TTS wrapper

Free, no API key required. Uses edge-tts library.
Async streaming TTS for generating audio lectures from text content.
"""
import asyncio
import logging
import os
import tempfile
import uuid

logger = logging.getLogger(__name__)

_VOICE = "zh-CN-XiaoxiaoNeural"


async def synthesize_to_file(
    text: str,
    output_path: str | None = None,
    voice: str = _VOICE,
) -> str:
    """Synthesize text to MP3 file. Returns file path.

    Args:
        text: Chinese text to synthesize (any length, auto-chunked)
        output_path: Target .mp3 path. If None, writes to static/audio/{uuid}.mp3
        voice: Edge TTS voice name. Default: zh-CN-XiaoxiaoNeural

    Returns:
        Absolute path to the generated MP3 file
    """
    import edge_tts

    if output_path is None:
        audio_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static", "audio"
        )
        os.makedirs(audio_dir, exist_ok=True)
        output_path = os.path.join(audio_dir, f"{uuid.uuid4().hex}.mp3")

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

    logger.info("Edge TTS: saved %d chars → %s", len(text), output_path)
    return output_path


async def synthesize_stream(
    text: str,
    voice: str = _VOICE,
):
    """Stream MP3 audio chunks from Edge TTS.

    Args:
        text: Chinese text to synthesize
        voice: Edge TTS voice name

    Yields:
        bytes: MP3 audio chunks
    """
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]


async def text_to_speech_bytes(text: str, voice: str = _VOICE) -> bytes:
    """Synthesize text and return full MP3 as bytes (for HTTP response)."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    parts: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            parts.append(chunk["data"])
    return b"".join(parts)
