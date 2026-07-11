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
import re
from typing import Any

logger = logging.getLogger(__name__)


# 教学"继续/下一个"显式信号 (与 supervisor._is_teaching_continue 对齐)
_TEACHING_CONTINUE_PATTERNS = [
    r'^(好|好的|可以|行|来|开始|没问题|嗯|OK|ok|yes|是|对|继续|下一个|下一节|接着|继续学|接着学|往下|往下学|学下一个|go on|next|continue|sure|yep|yeah|当然|必须的|搞起|来吧|开始吧|继续吧|OK吧)$',
    r'(开始|讲解|讲一下|学一下|详细|进入|说说|讲).*第[一二三四五六七八九十\d]+',
    r'第[一二三四五六七八九十\d]+\s*(天|节|课|章|节点|步)',
]


def _has_teaching_continue_signal(user_msg: str) -> bool:
    """检测用户消息是否包含教学"继续"信号"""
    if not user_msg:
        return False
    stripped = user_msg.strip()
    for pattern in _TEACHING_CONTINUE_PATTERNS:
        if re.search(pattern, stripped, re.IGNORECASE):
            return True
    return False


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
          2. 用户消息包含教学"继续"信号 ("好的", "继续", "下一个", "第X天")
          3. context 中显式标记 _explicit_teach=True (supervisor 显式授权)

        否则: 跳过教学启动, 走正常路径规划
    """
    tc = state.get("teaching_context") or {}

    # 条件 1: 教学上下文已存在
    if tc.get("mode") == "teaching":
        logger.debug("P0-B gate: 教学上下文已存在, 允许启动")
        return True

    # 条件 2: 用户显式继续信号
    try:
        from app.agents._msg_compat import last_msg_content
        user_msg = last_msg_content(state.get("messages", []))
        if _has_teaching_continue_signal(user_msg):
            logger.info("P0-B gate: 用户消息含教学继续信号, 允许启动 (msg='%s')",
                       user_msg[:50] if user_msg else "")
            return True
    except Exception as e:
        logger.debug("P0-B gate: 提取 user_msg 失败 (%s), 降级判断", e)

    # 条件 3: supervisor 显式授权
    if context.get("_explicit_teach"):
        logger.info("P0-B gate: supervisor 显式授权 _explicit_teach=True")
        return True

    # 默认: 拒绝启动, 走路径规划
    logger.info("P0-B gate: 拒绝启动 _teaching_init (无显式信号, 避免越权教学)")
    return False
