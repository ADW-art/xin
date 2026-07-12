"""教学流启动 gate - 防止 path_agent 越权自动启动 26 节点教学

设计 (P0-B 2026-07-11):
  - 即使 checkpoint 继承或 supervisor 错误标记 init_teaching=True,
    也必须有"显式信号"才启动教学
  - 显式信号 = (用户说了"继续/下一个/好的"等 OR 教学上下文已存在)
  - 防止用户问"帮我制定一个 Python 学习计划"被强行启动 26 节点教学循环

Usage (in path_agent.py):
    from app.agents._teaching_gate import should_init_teaching
    if context.get("init_teaching") and should_init_teaching(state, context):
        ...  # 走原 _teaching_init 流程
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def should_init_teaching(state: dict, context: dict) -> bool:
    """判断是否应该启动 _teaching_init 教学流程

    Args:
        state: AgentState
        context: state["context"]

    Returns:
        bool: True = 启动教学, False = 跳过 (默认做路径规划)

    Logic:
        必须满足以下**任一**条件:
          1. teaching_context 已存在 (mode == "teaching")
          2. 用户消息包含教学"继续"信号 (复用 shared_utils.is_teaching_continue)
          3. context 中显式标记 _explicit_teach=True (supervisor 显式授权)

        否则: 跳过教学启动, 走正常路径规划
    """
    tc = state.get("teaching_context") or {}

    # 条件 1: 教学上下文已存在
    if tc.get("mode") == "teaching":
        logger.debug("P0-B gate: 教学上下文已存在, 允许启动")
        return True

    # 条件 2: 用户显式继续信号 (P1-FIX: 复用 shared_utils.is_teaching_continue, 删除重复检测)
    try:
        from app.core.shared_utils import is_teaching_continue
        if is_teaching_continue(
            _get_user_msg(state),
            tc if tc.get("mode") == "teaching" else None
        ):
            logger.info("P0-B gate: 用户消息含教学继续信号, 允许启动")
            return True
    except Exception as e:
        logger.debug("P0-B gate: is_teaching_continue 失败 (%s), 降级判断", e)

    # 条件 3: supervisor 显式授权
    if context.get("_explicit_teach"):
        logger.info("P0-B gate: supervisor 显式授权 _explicit_teach=True")
        return True

    # 默认: 拒绝启动, 走路径规划
    logger.info("P0-B gate: 拒绝启动 _teaching_init (无显式信号, 避免越权教学)")
    return False


def _get_user_msg(state: dict) -> str:
    """从 state 中提取最后一条用户消息"""
    from app.agents._msg_compat import last_msg_content
    return last_msg_content(state.get("messages", []))
