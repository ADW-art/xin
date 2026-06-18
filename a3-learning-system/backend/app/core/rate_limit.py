"""
请求频率限制中间件
基于 Redis 滑动窗口（Sorted Set）+ 内存降级的双层限流，按用户身份区分限制级别

特性:
- 主 Redis Sorted Set 滑动窗口，支持多进程共享
- Redis 不可用时自动降级到内存 defaultdict（打印警告）
- 已认证用户按 user_id 限流（500/min），匿名用户按 IP 限流（60/min）
- 后台线程每 5 分钟清理过期条目（Redis ZREMRANGEBYSCORE / 内存裁剪）
- 不主动信任 X-Forwarded-For，仅 trust_proxy=True 时采纳
- 响应注入 X-RateLimit-Limit / X-RateLimit-Remaining / X-RateLimit-Reset 头
"""

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from fastapi import Request

from app.config import settings
from app.core.security import decode_access_token

logger = logging.getLogger(__name__)


@dataclass
class RateLimitState:
    """Rate limit check result, used for both enforcement and header generation."""
    allowed: bool
    limit: int
    remaining: int
    reset_at: int  # unix timestamp


class RateLimiter:
    """滑动窗口限流器（Redis Sorted Set 主 + 内存降级 + 身份区分）

    Usage:
        limiter = RateLimiter(
            auth_limit=500,      # requests/min for authenticated users
            anon_limit=60,       # requests/min for anonymous users
            window_seconds=60,
        )

        @app.middleware("http")
        async def rate_limit_middleware(request, call_next):
            state = limiter.check(request)
            if not state.allowed:
                return JSONResponse(status_code=429, ...)
            response = await call_next(request)
            for k, v in state.as_headers().items():
                response.headers[k] = v
            return response
    """

    REDIS_KEY_PREFIX = "ratelimit:"

    def __init__(
        self,
        auth_limit: int = 500,
        anon_limit: int = 60,
        window_seconds: int = 60,
    ):
        """
        Args:
            auth_limit: 已认证用户每分钟最大请求数
            anon_limit: 匿名用户每分钟最大请求数
            window_seconds: 滑动窗口大小（秒）
        """
        self.auth_limit = auth_limit
        self.anon_limit = anon_limit
        self.window = window_seconds
        self._clients: dict[str, list[float]] = defaultdict(list)
        self._redis_available: Optional[bool] = None  # None = untested

        # 启动后台清理线程（daemon，进程退出时自动结束）
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True, name="rate-limiter-cleanup"
        )
        self._cleanup_thread.start()

    # ── Public API ──────────────────────────────────────────

    def check(self, request: Request) -> RateLimitState:
        """检查并记录本次请求的限流状态。

        返回 RateLimitState，调用方据此决定是否放行并设置响应头。
        """
        identifier, limit = self._identify(request)
        now = time.time()
        reset_at = int(now + self.window)

        # 优先尝试 Redis
        if self._redis_available is not False:
            remaining = self._check_redis(identifier, limit, now)
            if remaining is not None:
                return RateLimitState(
                    allowed=(remaining >= 0),
                    limit=limit,
                    remaining=max(remaining, 0),
                    reset_at=reset_at,
                )

        # 降级到内存
        remaining = self._check_memory(identifier, limit, now)
        return RateLimitState(
            allowed=(remaining >= 0),
            limit=limit,
            remaining=max(remaining, 0),
            reset_at=reset_at,
        )

    # ── Identification ──────────────────────────────────────

    def _identify(self, request: Request) -> tuple[str, int]:
        """返回 (identifier, limit)。

        已认证用户使用 'user:{id}' 键（高限额），匿名用户使用 'ip:{addr}' 键（低限额）。
        """
        user_id = self._extract_user_id(request)
        if user_id is not None:
            return f"user:{user_id}", self.auth_limit

        ip = self._get_client_ip(request)
        return f"ip:{ip}", self.anon_limit

    def _extract_user_id(self, request: Request) -> Optional[int]:
        """从 Authorization 头的 JWT 中提取 user_id。未认证返回 None。"""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        payload = decode_access_token(token)
        if payload is None:
            return None

        try:
            return int(payload.get("sub", ""))
        except (ValueError, TypeError):
            return None

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端 IP（匿名请求用）。

        默认只信任直连 IP (request.client.host)，防止 X-Forwarded-For 伪造。
        仅当 settings.rate_limit_trust_proxy=True 且运行在可信反代后方时采纳代理头。
        """
        if settings.rate_limit_trust_proxy:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                return real_ip.strip()

        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    # ── Redis Backend (Sorted Set 滑动窗口) ─────────────────

    def _get_redis(self):
        """获取 Redis 连接。不可用时返回 None。首次连接后缓存可用性状态。"""
        if self._redis_available is False:
            return None
        try:
            import redis
            r = redis.from_url(settings.redis_url)

            if self._redis_available is None:
                r.ping()
                self._redis_available = True
                logger.info("Rate limiter using Redis backend")

            return r
        except Exception as e:
            if self._redis_available is None:
                self._redis_available = False
                logger.warning(
                    "Redis unavailable, rate limiter falling back to in-memory storage. "
                    "State will NOT be shared across processes. Error: %s", e
                )
            return None

    def _check_redis(self, identifier: str, limit: int, now: float) -> Optional[int]:
        """Redis Sorted Set 滑动窗口检查+记录。

        原子流水线:
          1. ZREMRANGEBYSCORE 清除窗口外的旧条目
          2. ZADD 添加当前请求时间戳
          3. ZCARD 获取窗口内请求数
          4. EXPIRE 设置键 TTL（3 倍窗口，兜底自动清理）

        Returns:
            剩余配额（int），Redis 不可用返回 None。
        """
        r = self._get_redis()
        if r is None:
            return None
        try:
            key = f"{self.REDIS_KEY_PREFIX}{identifier}"
            cutoff = now - self.window
            # 纳秒时间戳作为 member 保证唯一性（同一秒内多次请求不会冲突）
            member = str(time.time_ns())

            pipe = r.pipeline(transaction=True)
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zadd(key, {member: now})
            pipe.zcard(key)
            pipe.expire(key, self.window * 3)
            _, _, count, _ = pipe.execute()

            return limit - int(count)
        except Exception as e:
            logger.warning("Redis rate limit check failed, falling back to memory: %s", e)
            return None

    # ── In-Memory Backend ───────────────────────────────────

    def _check_memory(self, identifier: str, limit: int, now: float) -> int:
        """内存滑动窗口检查+记录。返回剩余配额。"""
        cutoff = now - self.window
        # 剪除过期条目
        self._clients[identifier] = [
            t for t in self._clients[identifier] if t > cutoff
        ]
        # 记录本次请求
        self._clients[identifier].append(now)
        return limit - len(self._clients[identifier])

    # ── Periodic Cleanup ────────────────────────────────────

    def _cleanup_loop(self):
        """后台 daemon 线程，每 5 分钟触发一次清理。"""
        while True:
            time.sleep(300)  # 5 minutes
            try:
                self._cleanup()
            except Exception:
                # 清理失败不影响主流程
                pass

    def _cleanup(self):
        """清理两种后端中的过期条目。"""
        now = time.time()
        cutoff = now - self.window

        # Redis: SCAN 遍历所有限流键，ZREMRANGEBYSCORE 清除过期条目
        r = self._get_redis()
        if r is not None:
            try:
                cursor = 0
                while True:
                    cursor, keys = r.scan(
                        cursor, match=f"{self.REDIS_KEY_PREFIX}*", count=100
                    )
                    if keys:
                        pipe = r.pipeline(transaction=False)
                        for key in keys:
                            pipe.zremrangebyscore(key, 0, cutoff)
                        pipe.execute()
                    if cursor == 0:
                        break
            except Exception:
                pass

        # 内存：裁剪过期时间戳，删除空列表
        stale_keys: list[str] = []
        for key, timestamps in list(self._clients.items()):
            self._clients[key] = [t for t in timestamps if t > cutoff]
            if not self._clients[key]:
                stale_keys.append(key)
        for key in stale_keys:
            del self._clients[key]
