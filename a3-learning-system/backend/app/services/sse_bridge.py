"""
SSE 桥接层 — 照搬 sse-starlette EventSourceResponse 架构

职责:
  1. StreamRequest: 协议化 SSE 流请求 (替代裸 dict stream_pending)
  2. 重复检测 + Spark token 清理 + 流完整性校验
  3. _bridge_stream: 同步 LLM → 异步 SSE 桥接

参考:
  - sse-starlette: ServerSentEvent dataclass 模式
  - OpenSpawn: BusBackend Protocol 分层设计
"""

import re
import json
import time
import hashlib as _hashlib
import asyncio
import logging

from app.utils.circuit_breaker import _llm_breaker, CircuitBreakerOpenError
import os
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_SENTINEL = object()

# 共享线程池 — 避免每次 SSE 请求创建新线程
_bridge_executor = ThreadPoolExecutor(
    max_workers=min(32, (os.cpu_count() or 1) * 4 + 1),
    thread_name_prefix="bridge_"
)


# ═══════════════════════════════════════════════════════════
# H7: StreamRequest — 照搬 sse-starlette ServerSentEvent dataclass
# ═══════════════════════════════════════════════════════════

@dataclass
class StreamRequest:
    """SSE 流请求协议 — 替代裸 dict stream_pending

    照搬 sse-starlette ServerSentEvent(data, event, id, retry) dataclass 设计:
    - 类型安全: 字段在定义时检查, 非运行时
    - 默认值: 语义合理的默认值
    - 无 dict 拼写错误风险
    """
    messages: list
    temperature: float = 0.5
    max_tokens: int = 4096
    use_safe: bool = True
    chunk_size: int = 2


# ═══════════════════════════════════════════════════════════
# P0-#1: 同请求去重
# ═══════════════════════════════════════════════════════════

_CONTENT_DEDUP_CACHE: dict[str, tuple[str, float]] = {}
_DEDUP_WINDOW_SEC = 5.0
_DEDUP_MAX_CACHE = 256


def is_duplicate_chunk(user_msg: str, content_chunk: str) -> bool:
    """同请求 5s 窗口内同前缀内容视为重复

    只检测长内容重复 (>=50 字符), 避免短 chunk 误判
    """
    if not content_chunk or len(content_chunk) < 50:
        return False
    key = _hashlib.md5(
        f"{user_msg[:80]}:{content_chunk[:80]}".encode("utf-8")
    ).hexdigest()
    now = time.time()
    if len(_CONTENT_DEDUP_CACHE) > _DEDUP_MAX_CACHE:
        cutoff = now - _DEDUP_WINDOW_SEC * 2
        for k in list(_CONTENT_DEDUP_CACHE.keys()):
            if _CONTENT_DEDUP_CACHE[k][1] < cutoff:
                _CONTENT_DEDUP_CACHE.pop(k, None)
    if key in _CONTENT_DEDUP_CACHE:
        cached, ts = _CONTENT_DEDUP_CACHE[key]
        if now - ts < _DEDUP_WINDOW_SEC:
            logger.warning("P0-#1 同请求去重触发: 5s 内重复 chunk (%d chars)", len(content_chunk))
            return True
    _CONTENT_DEDUP_CACHE[key] = (content_chunk, now)
    return False


# ═══════════════════════════════════════════════════════════
# P0-#2: Spark LLM 内部 highlight token 清理
# ═══════════════════════════════════════════════════════════

_SPARK_TOKEN_RE = re.compile(r'"[sS][a-z0-9]{1,2}">')


def clean_spark_tokens(text: str) -> str:
    """清理 Spark LLM 内部高亮 token, 保留纯代码"""
    if not text:
        return text
    cleaned = _SPARK_TOKEN_RE.sub("", text)
    cleaned = cleaned.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
    if len(cleaned) != len(text):
        logger.debug("P0-#2 Spark token 清理: 移除 %d 字符", len(text) - len(cleaned))
    return cleaned


# ═══════════════════════════════════════════════════════════
# P1-#5: 流式内容完整性校验
# ═══════════════════════════════════════════════════════════

class StreamIntegrityChecker:
    """检测流式内容是否完整 (无截断/无重复/无错乱)"""

    def __init__(self):
        self._chunks: list[str] = []
        self._total_len = 0
        self._last_chunk = ""

    def feed(self, chunk: str):
        self._chunks.append(chunk)
        self._total_len += len(chunk)
        self._last_chunk = chunk

    @property
    def is_suspicious(self) -> bool:
        """检测可疑模式"""
        if not self._chunks:
            return False
        # 截断检测: 最后 chunk 以不完整 token 结尾
        truncated_endings = ['"sk', '"sf', '"sc', '\\', '"""']
        for ending in truncated_endings:
            if self._last_chunk.rstrip().endswith(ending):
                logger.warning("P1-#5: 疑似截断 chunk ending=%r", self._last_chunk[-20:])
                return True
        return False

    def finalize(self) -> str:
        """返回完整内容并重置"""
        result = "".join(self._chunks)
        self._chunks.clear()
        self._total_len = 0
        self._last_chunk = ""
        return result


def stream_request_to_dict(sr: StreamRequest) -> dict:
    """StreamRequest → dict (兼容 chat.py event_stream 读取)"""
    return {
        "messages": sr.messages,
        "temperature": sr.temperature,
        "max_tokens": sr.max_tokens,
        "use_safe": sr.use_safe,
        "chunk_size": sr.chunk_size,
    }


# ═══════════════════════════════════════════════════════════
# _bridge_stream: 同步 LLM → 异步 SSE 桥接
# ═══════════════════════════════════════════════════════════

async def bridge_stream(spark, messages: list, temperature: float,
                        max_tokens: int, use_safe: bool = False,
                        chunk_size: int = 2):
    """线程安全队列桥接: 同步 chat_stream 转异步生成器

    照搬 sse-starlette EventSourceResponse 的 generator 模式。
    """
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _run():
        try:
            pre_collected = messages[0].get("__pre_collected__") if messages and isinstance(messages[0], dict) else None
            if pre_collected:
                for chunk in pre_collected:
                    if chunk:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
            else:
                _llm_breaker.acquire()
                try:
                    if use_safe:
                        from app.utils.llm_helper import safe_chat_stream
                        gen = safe_chat_stream(spark, messages, temperature=temperature,
                                               max_tokens=max_tokens, retries=2,
                                               fallback="服务繁忙，请稍后再试~")
                    else:
                        gen = spark.chat_stream(messages, temperature=temperature, max_tokens=max_tokens)
                    for chunk in gen:
                        if chunk:
                            loop.call_soon_threadsafe(queue.put_nowait, chunk)
                    _llm_breaker.record_success()
                except CircuitBreakerOpenError:
                    raise
                except Exception:
                    _llm_breaker.record_failure()
                    raise
        except CircuitBreakerOpenError as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    _bridge_executor.submit(_run)

    accumulated = ""
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=300)
        except asyncio.TimeoutError:
            logger.error("SSE stream timeout after 300s")
            if accumulated:
                yield accumulated
            yield f"event: v1.error\ndata: {json.dumps({'error': 'stream_timeout', 'message': '生成超时，请重试'})}\n\n"
            break
        if item is _SENTINEL:
            if accumulated:
                yield accumulated
            break
        if isinstance(item, Exception):
            if accumulated:
                yield accumulated
            raise item

        if chunk_size > 0:
            accumulated += item
            while len(accumulated) >= chunk_size:
                yield accumulated[:chunk_size]
                accumulated = accumulated[chunk_size:]
        else:
            yield item
