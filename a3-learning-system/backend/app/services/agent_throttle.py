"""
Agent 级速率限制 — 照搬 CrewAI RPMController token-bucket 算法

参考: CrewAI `crewai/utilities/rpm_controller.py`
- token-bucket 算法 (refill rate = max_rpm / 60)
- 线程安全 (threading.Lock)
- per-agent 配置 max_rpm

用法:
    from app.services.agent_throttle import get_throttle

    throttle = get_throttle("resource_agent", max_rpm=30)
    if not throttle.acquire(estimated_tokens=500):
        raise ResourceExhaustedError("Agent 限流")
"""

import time
import threading
import logging

logger = logging.getLogger(__name__)


class AgentThrottle:
    """Token-bucket 限流器 — 照搬 CrewAI RPMController 核心算法

    CrewAI 参考:
        class RPMController:
            def __init__(self, max_rpm: int = 60):
                self._max_rpm = max_rpm
                self._tokens = float(max_rpm)
                self._last_refill = time.monotonic()
                self._lock = threading.Lock()

            def _acquire(self) -> bool:
                with self._lock:
                    now = time.monotonic()
                    elapsed = now - self._last_refill
                    self._tokens = min(self._max_rpm, self._tokens + elapsed * (self._max_rpm / 60.0))
                    self._last_refill = now
                    if self._tokens >= 1.0:
                        self._tokens -= 1.0
                        return True
                    return False
    """

    def __init__(self, max_rpm: int = 30):
        self._max_rpm = max_rpm
        self._tokens = float(max_rpm)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    @property
    def max_rpm(self) -> int:
        return self._max_rpm

    @property
    def available_tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens

    def acquire(self, estimated_tokens: int = 1) -> bool:
        """尝试获取令牌 — 照搬 CrewAI RPMController._acquire()

        Args:
            estimated_tokens: 预估的 LLM 调用消耗 (请求数, 非 token 数)

        Returns:
            True  — 获取成功, 允许调用
            False — 令牌不足, 应等待或降级
        """
        with self._lock:
            self._refill()
            if self._tokens >= estimated_tokens:
                self._tokens -= estimated_tokens
                return True
            logger.warning("AgentThrottle: 令牌不足 (需要 %d, 可用 %.1f, max_rpm=%d)",
                           estimated_tokens, self._tokens, self._max_rpm)
            return False

    def _refill(self):
        """补充令牌 — 照搬 CrewAI 的时间比例 refill"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(float(self._max_rpm),
                           self._tokens + elapsed * (self._max_rpm / 60.0))
        self._last_refill = now

    def reset(self):
        """重置令牌桶到满"""
        with self._lock:
            self._tokens = float(self._max_rpm)
            self._last_refill = time.monotonic()


# 全局实例 — 模块级单例 (照搬 CrewAI 的模块级 RPMController)
_throttles: dict[str, AgentThrottle] = {}
_throttle_lock = threading.Lock()

# per-agent 默认 RPM 配置 (照搬 CrewAI per-agent max_rpm)
_DEFAULT_RPM: dict[str, int] = {
    "resource_agent": 30,
    "question_agent": 30,
    "evaluation_agent": 30,
    "path_agent": 30,
    "profile_agent": 30,
    "chat_agent": 60,
    "supervisor": 60,
}


def get_throttle(agent_name: str, max_rpm: int | None = None) -> AgentThrottle:
    """获取或创建 agent 的限流器 — 模块级单例模式

    Args:
        agent_name: agent 名称 (用于区分不同 agent 的限流策略)
        max_rpm: 每分钟最大请求数, None 则使用默认值
    """
    with _throttle_lock:
        if agent_name not in _throttles:
            rpm = max_rpm if max_rpm is not None else _DEFAULT_RPM.get(agent_name, 30)
            _throttles[agent_name] = AgentThrottle(max_rpm=rpm)
            logger.info("AgentThrottle: 为 '%s' 创建限流器 (max_rpm=%d)", agent_name, rpm)
        return _throttles[agent_name]


def reset_all_throttles():
    """重置所有限流器 (测试用)"""
    with _throttle_lock:
        for t in _throttles.values():
            t.reset()
