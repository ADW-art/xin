"""Stale One-Shot Flags 集中管理 (P1-B 2026-07-11)

问题:
  历史修复中, 一次性标志 (init_teaching / teaching_continue 等) 在 chat.py:430
  被硬编码列表清除. 如果新增一次性标志, 必须同时修改 3 处:
    1. 设置标志的代码
    2. chat.py 的 _stale_one_shot_flags 列表
    3. clean_checkpoint_stale_flags.py 的 _stale_flags tuple

  任何一处遗漏都会导致"残留标志跨会话继承"bug.

解决:
  集中所有一次性标志在本文件, 提供统一的清除接口.
  chat.py 和 clean_checkpoint_stale_flags.py 都 import 此模块.

Usage:
    from app.agents._stale_flags import STALE_ONE_SHOT_FLAGS, clear_stale_flags

    # 清除 state 字典中所有一次性标志 (in-place, 不返回新 dict)
    clear_stale_flags(state.get("context", {}))

    # 清除多个字典
    for d in [ctx, tc, ao]:
        clear_stale_flags(d)
"""
import logging
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)


# 一次性标志集中表 (添加新标志时, 只需修改这里)
STALE_ONE_SHOT_FLAGS: frozenset[str] = frozenset({
    # === 教学流 ===
    "init_teaching",                # 启动 26 节点教学循环 (P0-1 修复)
    "teaching_continue",            # 用户说"继续"触发下一节点
    "replan_path",                  # 路径动态重规划信号
    "_replan_reason",               # replan_path 的触发原因 (无 replan_path 时残留无意义)
    "teach_target_index",           # 指定教学节点索引
    "_explicit_teach",              # P2-1 (2026-07-12): supervisor 显式教学授权标志

    # === 意图/路由 ===
    "_new_intent_handled",          # 标记新意图已处理 (避免教学流劫持)
    "profile_first",                # 画像优先流程标记
    "_qa_stage",                    # QA 协作链阶段标记 (first_review / refinement)
    "_bkt_relevant",                # evaluation 路由标记

    # === 资源生成 ===
    # _quality_retry 已废弃 (P2 2026-07-13: 质量门不再自动重生成)

    # === 内部防重入 ===
    "_agent_lock",                  # 防止并发 agent 调用
    "_supervisor_lock",             # supervisor 防重入
})


def clear_stale_flags(*dicts: Mapping[str, Any]) -> int:
    """清除给定字典中的所有一次性标志 (in-place).

    Args:
        *dicts: 任意数量的字典, 通常是 state["context"] / state["teaching_context"] /
                state["agent_outputs"]["xxx"] 等.

    Returns:
        清除的标志数量

    Examples:
        >>> ctx = {"init_teaching": True, "topic": "Python"}
        >>> clear_stale_flags(ctx)
        1
        >>> ctx
        {"topic": "Python"}
    """
    if not dicts:
        return 0
    count = 0
    for d in dicts:
        if not isinstance(d, dict):
            continue
        for flag in STALE_ONE_SHOT_FLAGS:
            if flag in d:
                d.pop(flag, None)
                count += 1
    if count > 0:
        logger.debug("P1-B clear_stale_flags: 清除了 %d 个一次性标志", count)
    return count


def is_stale_flag(key: str) -> bool:
    """判断一个 key 是否为一次性标志"""
    return key in STALE_ONE_SHOT_FLAGS


def filter_stale_keys(d: Mapping[str, Any]) -> list[str]:
    """返回字典中所有一次性标志的 key 列表 (不删除)"""
    if not isinstance(d, dict):
        return []
    return [k for k in d.keys() if is_stale_flag(k)]


# 显式 alias, 兼容旧 API
ONE_SHOT_FLAGS = STALE_ONE_SHOT_FLAGS
cleanup_one_shot_flags = clear_stale_flags
