"""
安全模块

作用：
  提供密码加密/验证和 JWT 令牌的创建/解析/黑名单检查功能

关联文件：
  api/auth.py  ← 注册/登录/登出接口依赖本模块
  api/chat.py  ← 解析 JWT 做可选认证
"""
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext
from app.config import settings

logger = logging.getLogger(__name__)

# bcrypt 密码哈希算法
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 加密"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码是否与哈希值匹配"""
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """创建 JWT 访问令牌（含 jti 唯一标识，用于登出黑名单）"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    to_encode.update({"exp": expire, "jti": uuid.uuid4().hex})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """解析 JWT 令牌，失败返回 None"""
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except Exception as e:
        logger.warning("JWT decode failed: %s", e)
        return None


def is_token_blacklisted(jti: str) -> bool:
    """检查 JWT token 是否在黑名单中（Redis 存储）

    用于登出后阻止旧 token 继续使用。
    Redis 不可用时降级为允许（不阻塞正常请求）。
    """
    if not jti:
        return False
    try:
        r = _get_redis()
        return bool(r.exists(f"blacklist:{jti}"))
    except Exception as e:
        logger.warning("Redis blacklist check failed (degraded to allow): %s", e)
        return False  # Redis 不可用时降级为允许


def add_to_blacklist(jti: str, expire_seconds: int | None = None) -> bool:
    """将 token 的 jti 加入黑名单

    Args:
        jti: JWT ID
        expire_seconds: 黑名单过期时间（秒），默认与 JWT 过期时间一致

    Returns:
        True 表示成功加入，False 表示操作失败（Redis 不可用）
    """
    if not jti:
        return False
    try:
        r = _get_redis()
        expire = expire_seconds or (settings.jwt_expire_minutes * 60)
        r.setex(f"blacklist:{jti}", expire, "1")
        return True
    except Exception as e:
        logger.warning("Redis blacklist add failed: %s", e)
        return False

# ── 共享 Redis 连接池（供 security.py / chat.py / supervisor.py 复用）──
import redis as _redis_mod
_redis_pool = None


def _get_redis():
    """获取 Redis 客户端（复用连接池，避免每次调用创建新 TCP 连接）"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = _redis_mod.ConnectionPool.from_url(settings.redis_url, max_connections=10)
    return _redis_mod.Redis(connection_pool=_redis_pool)
