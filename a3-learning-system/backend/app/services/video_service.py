"""T3 Video Generation — Slide + Audio + MP4 Video for the A3 learning system.

Two-tier API:
  gen(script_text)     → base64 slides + TTS audio for SlidePlayer (existing, unchanged)
  gen_mp4(script_text) → real MP4 video file via FFmpeg (new)

Pipeline (gen_mp4):
  1. Parse markdown script into slides (## and --- delimiters)
  2. For each slide: PIL render → PNG + TTS synthesize → MP3
  3. FFmpeg: PNG + MP3 → MP4 segment per slide
  4. FFmpeg concat: all segments → final MP4
  5. Upload to storage (MinIO if available, local static/ otherwise)
  6. Return video URL + metadata

Requirements: FFmpeg installed on the system path (choco install ffmpeg / apt install ffmpeg)
"""

import base64
import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── Constants ──
_W, _H = 1280, 720
_BG = (255, 255, 255)
_AC = (37, 99, 235)

# ── Font resolution (Windows → Linux CJK → Latin fallback → PIL default) ──
# Linux/Debian CJK: sudo apt install fonts-wqy-microhei fonts-noto-cjk
_FONT_PATHS = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    # ── Linux CJK fonts (Chinese/Japanese/Korean glyph support) ──
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    # ── Latin fallbacks ──
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]
_FP = None
for _candidate in _FONT_PATHS:
    if os.path.exists(_candidate):
        _FP = _candidate
        break
if not _FP:
    logger.warning("No system CJK font found; using PIL default (may lack Chinese glyphs)")


# ═══════════════════════════════════════════════════════
#  Shared helpers (used by both gen() and gen_mp4())
# ═══════════════════════════════════════════════════════

def _font(sz):
    """Resolve a PIL ImageFont at size sz."""
    try:
        return ImageFont.truetype(_FP, sz) if _FP else ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def _tts_b64(txt: str) -> str | None:
    """TTS → base64-encoded MP3 bytes (for the old slide show path)."""
    try:
        from app.services.tts_service import synthesize_speech
        a = synthesize_speech(txt[:200])
        if a:
            return base64.b64encode(a).decode()
    except Exception as e:
        logger.warning("TTS:%s", e)
    return None


def _tts_bytes(txt: str) -> bytes | None:
    """TTS → raw MP3 bytes (for the gen_mp4 pipeline)."""
    try:
        from app.services.tts_service import synthesize_speech
        return synthesize_speech(txt[:200])
    except Exception as e:
        logger.warning("TTS (bytes):%s", e)
        return None


def _parse_slides(script_text: str) -> list[dict]:
    """Parse markdown script into a list of {n, t, b, c, d} slide dicts.

    Delimiters: ## header or --- horizontal rule.
    Code blocks (```) are extracted into the 'c' field.
    """
    N = chr(10)
    raw_sections: list[str] = []
    cur: list[str] = []

    for line in script_text.split(N):
        s = line.strip()
        if s.startswith("##") or s.startswith("---"):
            if cur:
                raw_sections.append(N.join(cur))
                cur = []
            cur.append(line)
        else:
            cur.append(line)
    if cur:
        raw_sections.append(N.join(cur))

    parsed: list[dict] = []
    for sec_text in raw_sections:
        sec_text = sec_text.strip()
        if not sec_text or len(sec_text) < 10:
            continue
        lines = sec_text.split(N)
        title = lines[0].strip().strip("#").strip() or "内容"
        bl: list[str] = []
        cl: list[str] = []
        buf: list[str] = []
        in_code = False
        for l in lines[1:]:
            s = l.strip()
            if s.startswith("`" * 3):
                if in_code:
                    cl.append(N.join(buf))
                    buf = []
                    in_code = False
                else:
                    in_code = True
            elif in_code:
                buf.append(l)
            else:
                bl.append(l)
        bt = N.join(b for b in bl if b.strip()).strip()[:500]
        ct = N.join(cl).strip()[:300]
        dur = max(5, min(30, (len(bt) + len(ct) // 3) // 4 + 2))
        parsed.append({"n": len(parsed) + 1, "t": title, "b": bt, "c": ct, "d": dur})

    if not parsed:
        parsed.append({
            "n": 1, "t": "内容",
            "b": script_text[:500], "c": "",
            "d": min(30, max(10, len(script_text) // 10)),
        })
    return parsed


# ═══════════════════════════════════════════════════════
#  Old-gen slide render (kept for backward compat)
# ═══════════════════════════════════════════════════════

def _render_b64(s: dict) -> str:
    """Render a slide as a base64-encoded PNG (SlidePlayer path)."""
    img = Image.new("RGB", (_W, _H), _BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, _W, 80], fill=_AC)
    d.text((40, 20), s.get("t", ""), fill=(255, 255, 255), font=_font(36))
    y = 100
    for l in s.get("b", "").split(chr(10))[:12]:
        d.text((40, y), l[:80], fill=(33, 33, 33), font=_font(24))
        y += 30
    for i, l in enumerate(s.get("c", "").split(chr(10))[:8]):
        d.text((56, y + 8 + i * 24), l[:60], fill=(80, 80, 80), font=_font(18))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def gen(script_text: str) -> dict:
    """Generate slide-deck + base64 audio data for the SlidePlayer frontend.

    Returns dict with keys: slides, audio, total_dur, cnt.
    """
    parsed = _parse_slides(script_text)
    res, aud, tot = [], [], 0
    for s in parsed:
        img = _render_b64(s)
        audio = _tts_b64(s["t"] + "." + s["b"][:200])
        aud.append({"n": s["n"], "b64": audio or "", "d": s["d"]})
        res.append({"n": s["n"], "t": s["t"], "b": s["b"], "c": s["c"], "img": img})
        tot += s["d"]
    return {"slides": res, "audio": aud, "total_dur": tot, "cnt": len(res)}


# ═══════════════════════════════════════════════════════
#  MP4 generation helpers
# ═══════════════════════════════════════════════════════

def _check_ffmpeg() -> bool:
    """Return True when ffmpeg is on PATH."""
    return shutil.which("ffmpeg") is not None


def _render_slide_png(slide: dict) -> bytes:
    """Render a single slide as PNG bytes (enhanced layout)."""
    img = Image.new("RGB", (_W, _H), _BG)
    d = ImageDraw.Draw(img)

    # ── Header bar ──
    d.rectangle([0, 0, _W, 80], fill=_AC)
    title = slide.get("t", "幻灯片")[:50]
    slide_n = slide.get("n", 1)
    d.text((40, 22), f"#{slide_n}  {title}", fill=(255, 255, 255), font=_font(34))

    # ── Body text ──
    y = 100
    body = slide.get("b", "")[:800]
    for line in body.split(chr(10))[:14]:
        line = line.strip()[:100]
        if not line:
            y += 15
            continue
        # Bold detection
        if line.startswith("**") and line.rstrip().endswith("**"):
            clean = line.strip("* ").strip()
            d.text((40, y), clean, fill=(33, 33, 33), font=_font(26))
        else:
            d.text((40, y), line, fill=(55, 55, 55), font=_font(22))
        y += 34
        if y > _H - 100:
            break

    # ── Code block ──
    code = slide.get("c", "")
    if code and y < _H - 80:
        y += 10
        code_h = min(160, 24 + len(code.split(chr(10))[:8]) * 24)
        d.rectangle([40, y, _W - 40, y + code_h], fill=(245, 247, 250), outline=(220, 225, 230))
        for i, cline in enumerate(code.split(chr(10))[:6]):
            d.text((52, y + 6 + i * 22), cline[:85], fill=(70, 70, 80), font=_font(17))

    # ── Footer ──
    d.text((40, _H - 44), "A3 个性化学习系统  |  AI 生成教学视频", fill=(180, 180, 180), font=_font(14))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _generate_silent_mp3(duration_sec: float, output_path: str) -> bool:
    """Generate a silent MP3 file of given duration via FFmpeg."""
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
            "-t", str(duration_sec), "-acodec", "libmp3lame", "-b:a", "64k",
            output_path,
        ], capture_output=True, text=True, timeout=30, check=True)
        return True
    except Exception as e:
        logger.warning("Silent MP3 generation failed: %s", e)
        return False


def _generate_slide_video(
    png_path: str, audio_path: str, duration: float, output_path: str,
) -> None:
    """FFmpeg: one PNG (looped) + one MP3 → single MP4 segment."""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", png_path,
        "-i", audio_path,
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest", "-t", str(duration),
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if result.returncode != 0:
        logger.error("FFmpeg slide error (rc=%s): %s", result.returncode, result.stderr[-500:])
        raise RuntimeError("FFmpeg 单页视频生成失败")


def _concat_videos(segment_paths: list[str], output_path: str) -> None:
    """Concatenate MP4 segments via the FFmpeg concat demuxer."""
    concat_file = output_path + ".concat.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for sp in segment_paths:
            # Use forward slashes (FFmpeg on Windows also accepts them)
            f.write(f"file '{sp.replace(chr(92), '/')}'\n")

    try:
        result = subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_file, "-c", "copy", output_path,
        ], capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            logger.error("FFmpeg concat error (rc=%s): %s", result.returncode, result.stderr[-500:])
            raise RuntimeError("FFmpeg 视频合并失败")
    finally:
        try:
            os.remove(concat_file)
        except OSError:
            pass


def _get_static_dir() -> str:
    """Absolute path to backend/static/videos/ (created on demand)."""
    d = os.path.join(os.path.dirname(__file__), "..", "..", "static", "videos")
    os.makedirs(d, exist_ok=True)
    return d


def _upload_to_storage(file_path: str, filename: str) -> str:
    """Place the final MP4 in static/videos/ and return the relative URL.

    If the 'minio' package is installed and credentials are configured,
    also upload a copy to MinIO; the return URL remains the local one for
    reliability.
    """
    # ── Always save to local static/ ──
    static_dir = _get_static_dir()
    dest = os.path.join(static_dir, filename)
    if os.path.abspath(file_path) != os.path.abspath(dest):
        shutil.copy2(file_path, dest)
    logger.info("Video saved to %s", dest)

    # ── Best-effort MinIO upload ──
    try:
        from minio import Minio  # type: ignore
        from app.config import settings

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
        bucket = "a3-videos"
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.fput_object(bucket, filename, file_path, content_type="video/mp4")
        logger.info("Video also uploaded to MinIO bucket=%s", bucket)
    except ImportError:
        logger.debug("MinIO package not installed; video served from local static/")
    except Exception as e:
        logger.warning("MinIO upload skipped: %s", e)

    return f"/static/videos/{filename}"


# ═══════════════════════════════════════════════════════
#  Public API — gen_mp4
# ═══════════════════════════════════════════════════════

def gen_mp4(script_text: str) -> dict:
    """Generate a real MP4 video from a video_script markdown text.

    Steps:
      1. Parse script into slides
      2. For each slide: render PNG + synthesize TTS audio (or silent fallback)
      3. FFmpeg: PNG + MP3 → MP4 segment per slide
      4. FFmpeg concat: all segments → final MP4
      5. Upload to static storage → return URL

    Returns:
        {
            "video_url"    : str | None,   # e.g. "/static/videos/a3_video_abc123.mp4"
            "duration_sec" : float,        # total duration estimate
            "slide_count"  : int,          # number of slides
            "slides"       : list[dict],   # per-slide metadata
            "filename"     : str,          # generated filename
            "error"        : str | None,   # present only on failure
        }

    Error cases return with "error" set and video_url=None.
    """
    # ── Guard: FFmpeg required ──
    if not _check_ffmpeg():
        return {
            "error": "FFmpeg 未安装，无法生成视频。Windows: choco install ffmpeg  |  Linux: sudo apt install ffmpeg",
            "video_url": None, "duration_sec": 0, "slide_count": 0, "slides": [],
            "filename": "",
        }

    # ── Step 1: Parse ──
    parsed = _parse_slides(script_text)

    # ── Step 2–3: Render + TTS + FFmpeg per slide ──
    tmpdir = tempfile.mkdtemp(prefix="a3_video_")
    segment_paths: list[str] = []
    total_duration = 0.0
    rendered_slides: list[dict] = []
    s_suffix = uuid.uuid4().hex[:6]

    try:
        for slide in parsed:
            sn = slide["n"]
            title = slide["t"]
            duration = float(slide["d"])
            total_duration += duration

            # 2a. Render PNG
            png_path = os.path.join(tmpdir, f"s{s_suffix}_{sn:03d}.png")
            png_bytes = _render_slide_png(slide)
            with open(png_path, "wb") as f:
                f.write(png_bytes)

            # 2b. Synthesize TTS (or silent fallback)
            tts_text = f"{title}。{slide['b'][:180]}"
            mp3_bytes = _tts_bytes(tts_text)
            audio_path = os.path.join(tmpdir, f"a{s_suffix}_{sn:03d}.mp3")

            if mp3_bytes:
                with open(audio_path, "wb") as f:
                    f.write(mp3_bytes)
            else:
                ok = _generate_silent_mp3(duration, audio_path)
                if not ok:
                    # Last-resort: write a minimal valid MP3 bytestream
                    with open(audio_path, "wb") as f:
                        f.write(b"\xff\xfb\x90\x00" * 1000)

            # 3. PNG + MP3 → MP4 segment
            seg_path = os.path.join(tmpdir, f"v{s_suffix}_{sn:03d}.mp4")
            _generate_slide_video(png_path, audio_path, duration, seg_path)
            segment_paths.append(seg_path)

            rendered_slides.append({
                "n": sn, "t": title,
                "b": slide["b"][:120],
                "d": duration,
            })

        # ── Step 4: Concat all segments → final MP4 ──
        output_filename = f"a3_video_{uuid.uuid4().hex[:8]}.mp4"
        final_path = os.path.join(tmpdir, output_filename)

        if len(segment_paths) == 1:
            shutil.copy2(segment_paths[0], final_path)
        else:
            _concat_videos(segment_paths, final_path)

        # ── Step 5: Upload ──
        video_url = _upload_to_storage(final_path, output_filename)

        return {
            "video_url": video_url,
            "duration_sec": round(total_duration, 1),
            "slide_count": len(rendered_slides),
            "slides": rendered_slides,
            "filename": output_filename,
        }

    except Exception as exc:
        logger.exception("gen_mp4 failed")
        return {
            "error": f"视频生成失败: {exc}",
            "video_url": None, "duration_sec": 0, "slide_count": 0, "slides": [],
            "filename": "",
        }
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
