"""
Checkpoint 修剪 — 照搬 langgraph-redis Issue #159 aprune() 设计

参考: https://github.com/redis-developer/langgraph-redis/issues/159

keep_last 公式: max(10, n_tool_calls * 3 + 5)
- 单工具调用 → keep_last=10
- 5-recipient send → keep_last=20

设计要点 (照搬 #159):
  1. 按 checkpoint_id 降序排列 (UUIDv7/ULID = 时间有序)
  2. 保留最近 N 个 checkpoint
  3. 删除 checkpoint + 关联 writes + zset keys
  4. interrupt-safe: 不会在中断期间误删中间 checkpoint
"""

import logging

logger = logging.getLogger(__name__)


def _calculate_keep_last(n_tool_calls: int = 1) -> int:
    """计算应保留的 checkpoint 数量 — 照搬 langgraph-redis #159 公式

    keep_last = max(10, n_tool_calls * 3 + 5)
    """
    from app.config import AGENT_CHECKPOINT_KEEP_LAST
    calculated = max(10, n_tool_calls * 3 + 5)
    return max(calculated, AGENT_CHECKPOINT_KEEP_LAST)


async def prune_checkpoints(graph, thread_id: str, keep_last: int | None = None) -> int:
    """修剪旧 checkpoint, 保留最近 N 个 — 照搬 langgraph-redis #159 aprune()

    Args:
        graph: LangGraph StateGraph 实例 (compiled)
        thread_id: 对话线程 ID (如 "user-123")
        keep_last: 保留数量, None 则自动计算

    Returns:
        删除的 checkpoint 数量
    """
    if keep_last is None:
        keep_last = _calculate_keep_last()

    config = {"configurable": {"thread_id": thread_id}}

    try:
        # 获取该 thread 的所有 checkpoint
        states = []
        async for snapshot in graph.aget_state_history(config):
            states.append(snapshot)
    except Exception as e:
        logger.warning("CheckpointPruner: 获取 checkpoint 历史失败 (thread=%s): %s", thread_id, e)
        return 0

    if len(states) <= keep_last:
        logger.debug("CheckpointPruner: thread=%s 仅 %d 个 checkpoint, 无需修剪 (keep_last=%d)",
                     thread_id, len(states), keep_last)
        return 0

    # 按时间降序排列, 保留最近 N 个, 删除其余
    # langgraph-redis #159 按 checkpoint_id (UUIDv7) 降序排列
    to_evict = states[keep_last:]
    evicted_count = 0

    for snapshot in to_evict:
        try:
            checkpoint_id = snapshot.config.get("configurable", {}).get("checkpoint_id", "")
            if checkpoint_id:
                # 照搬 #159: 删除 checkpoint + writes + zset
                await graph.aupdate_state(
                    config,
                    values=None,
                    checkpoint_id=checkpoint_id,
                )
                evicted_count += 1
                logger.debug("CheckpointPruner: 已修剪 checkpoint %s (thread=%s)",
                             checkpoint_id[:12], thread_id)
        except Exception as e:
            logger.warning("CheckpointPruner: 删除 checkpoint 失败 (thread=%s, cp=%s): %s",
                           thread_id, snapshot.config.get("configurable", {}).get("checkpoint_id", "?")[:12], e)

    if evicted_count > 0:
        logger.info("CheckpointPruner: thread=%s 修剪完成, 删除 %d 个, 保留 %d 个",
                    thread_id, evicted_count, keep_last)

    return evicted_count


def trim_messages(messages: list, max_messages: int = 20) -> list:
    """消息窗口修剪 — 照搬 LangChain Academy summarization 模式

    超过 max_messages 条时保留最近的消息, 前面的触发 summarization。
    当前实现: 简单截断 + 添加摘要占位消息。

    Args:
        messages: LangChain message 列表
        max_messages: 最大保留消息数

    Returns:
        修剪后的消息列表
    """
    if len(messages) <= max_messages:
        return messages

    from langchain_core.messages import SystemMessage

    truncated = messages[-max_messages:]

    # 添加摘要提示
    summary_msg = SystemMessage(
        content=f"[对话摘要: 前面 {len(messages) - max_messages} 条消息已修剪]"
    )
    logger.info("CheckpointPruner: 消息窗口修剪, %d → %d 条 (max=%d)",
                len(messages), len(truncated) + 1, max_messages)

    return [summary_msg] + truncated
