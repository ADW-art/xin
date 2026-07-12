"""
熔断器 (Circuit Breaker) — LLM 调用保护

状态机: CLOSED → OPEN → HALF_OPEN → CLOSED
参照 agentguard PyPI 的 CircuitBreaker 模式实现。

CLOSED:    正常状态，请求直通。连续失败达阈值时切换到 OPEN。
OPEN:      熔断状态，拒绝所有请求。等待 recovery_timeout 后切换到 HALF_OPEN。
HALF_OPEN: 半开状态，允许一个试探请求。成功 → CLOSED，失败 → OPEN。

用法:
    from app.utils.circuit_breaker import CircuitBreaker

    _llm_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)

    try:
        raw = _llm_breaker.call(spark.chat_sync, messages, temperature=0.3)
    except CircuitBreakerOpenError:
        # 熔断器开启，使用降级响应
        raw = fallback_response()
"""

import time
import threading
import logging

logger = logging.getLogger(__name__)


class CircuitBreakerOpenError(Exception):
    """熔断器开启时抛出的异常"""
    pass


class CircuitBreaker:
    """LLM 调用熔断器

    参数:
        failure_threshold: 连续失败次数阈值，达到后熔断
        recovery_timeout: 熔断后等待多少秒进入 HALF_OPEN
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        """当前状态 (只读)"""
        return self._state

    @property
    def failure_count(self) -> int:
        """当前连续失败次数 (只读)"""
        return self._failure_count

    def call(self, func, *args, **kwargs):
        """包装函数调用，自动应用熔断逻辑

        Args:
            func: 要调用的函数
            *args, **kwargs: 传递给 func 的参数

        Returns:
            func 的返回值

        Raises:
            CircuitBreakerOpenError: 熔断器处于 OPEN 状态时
        """
        self.acquire()

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise

    def acquire(self):
        """流式调用前检查熔断器状态。OPEN 时抛 CircuitBreakerOpenError，到期则转 HALF_OPEN。"""
        with self._lock:
            if self._state == "OPEN":
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = "HALF_OPEN"
                    logger.info("CircuitBreaker: OPEN → HALF_OPEN (恢复期到)")
                else:
                    raise CircuitBreakerOpenError(
                        f"熔断器开启中，剩余 {self.recovery_timeout - (time.time() - self._last_failure_time):.0f}s"
                    )

    def record_success(self):
        """流式调用成功后记录，重置熔断器。"""
        self._on_success()

    def record_failure(self):
        """流式调用失败后记录，递增失败计数。"""
        self._on_failure()

    def _on_success(self):
        """调用成功时重置状态"""
        with self._lock:
            self._failure_count = 0
            if self._state == "HALF_OPEN":
                self._state = "CLOSED"
                logger.info("CircuitBreaker: HALF_OPEN → CLOSED (试探成功)")

    def _on_failure(self):
        """调用失败时递增计数器"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == "HALF_OPEN" or (
                self._state == "CLOSED" and self._failure_count >= self.failure_threshold
            ):
                self._state = "OPEN"
                logger.warning(
                    "CircuitBreaker: → OPEN (连续失败 %d 次, 恢复等待 %.0fs)",
                    self._failure_count,
                    self.recovery_timeout,
                )

    def reset(self):
        """手动重置熔断器到 CLOSED 状态"""
        with self._lock:
            self._failure_count = 0
            self._state = "CLOSED"
            logger.info("CircuitBreaker: 手动重置 → CLOSED")


# 模块级 LLM 熔断器实例 — 所有 agent 共用
# failure_threshold=3: 连续 3 次 LLM 失败后熔断
# recovery_timeout=30: 30 秒后进入 HALF_OPEN 试探
_llm_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
