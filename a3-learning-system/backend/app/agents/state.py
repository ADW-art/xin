"""
AgentState — 多智能体共享状态 (Pydantic v2)

升级要点:
  - TypedDict → Pydantic BaseModel: 运行时类型验证 + 默认值
  - context/agent_outputs 使用 Field(default_factory) 确保独立实例
  - teaching_context 承载 KG-Node 教学流程状态
  - 支持 LangGraph checkpoint 持久化 (SQLite)
"""

from __future__ import annotations
from typing import Optional, Annotated
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


def _last_value_reducer(old, new):
    """Reducer: 并行节点更新同一字段时,取最新值(覆盖式)

    解决 LangGraph 报错: 'At key current_agent: Can receive only one value per step'
    原因: Send API 并行执行时,多个节点都尝试更新 current_agent
    解决: 用 reducer 接受最新值(后运行的覆盖先运行的)

    P0-FIX (2026-07-12): new is None 时保留 old, 防止跨轮次 checkpoint
    合并时 None 覆盖有效值 (next_agent "END" → None → supervisor_router 返回 None
    不在条件边映射中 → 图挂起)
    """
    return new if new is not None else old


def _concat_str_reducer(old: str, new: str) -> str:
    """Reducer: 字符串拼接(适用于 stream_buffer)

    多个并行 Agent 同时写 stream_buffer 时,把内容拼接起来
    而不是覆盖 — 保证用户能看到所有并行 Agent 的输出

    当 new 为空字符串时, 视为清空信号 — 防止旧内容跨节点累积。
    Supervisor 每次返回 stream_buffer="" 即清空上一次的缓冲区。
    """
    if not new:
        return ""
    return (old or "") + (new or "")


def _merge_dict_reducer(old: dict, new: dict) -> dict:
    """Reducer: dict 合并(适用于 agent_outputs / context)

    多个并行 Agent 同时写 dict 时,后写的字段覆盖先写的,
    但不覆盖其他 Agent 写的字段。

    P0-2 (2026-07-12): 支持显式清除 — 当 new 包含 {"_CLEAR_": True} 时,
    忽略旧值, 直接返回 new 中除 _CLEAR_ 之外的字段。
    这解决了 initial_state agent_outputs={} 被 _merge_dict_reducer
    旧值覆盖的 Bug (merge_dict 中 {} 不覆盖旧 dict)。
    """
    if new.get("_CLEAR_"):
        return {k: v for k, v in new.items() if k != "_CLEAR_"}
    return {**(old or {}), **(new or {})}


def _teaching_context_reducer(old: dict | None, new: dict | None) -> dict | None:
    """Reducer: teaching_context 专用合并, None 表示清空

    P0-FIX (2026-07-12): _merge_dict_reducer 将 None 静默转为 {},
    导致 path_agent 和 supervisor 无法清除 teaching_context,
    跨轮次 checkpoint 残留触发自动教学链.
    """
    if new is None:
        return None
    return {**(old or {}), **(new or {})}


def _concat_list_reducer(old: list, new: list) -> list:
    """Reducer: list 拼接(适用于 trace)

    多个节点追加 trace 条目时,合并为一个列表。
    P1-FIX: 限制最大 100 条, 防止跨轮次无界增长导致 checkpoint 膨胀。
    """
    merged = (old or []) + (new or [])
    if len(merged) > 100:
        return merged[-100:]
    return merged


class AgentState(BaseModel):
    """多智能体共享状态 — Pydantic v2 验证

    通过 LangGraph 图传递, 每个 Agent 节点读取/写入。
    context 和 agent_outputs 在各节点中通过 {**old, **new} 模式合并。
    """

    # ── 消息历史 (LangGraph add_messages reducer 自动合并) ──
    messages: Annotated[list, add_messages] = Field(default_factory=list)

    # ── Agent 路由 ──
    # 用 reducer 接受并行节点更新: 协同节点 (qa_join/rc_join/path_join) 都会写 current_agent
    current_agent: Annotated[str, _last_value_reducer] = "supervisor"  # 当前激活的 Agent
    next_agent: Annotated[Optional[str], _last_value_reducer] = None     # Supervisor 的路由决策

    # ── 用户上下文 ──
    user_profile: Optional[dict] = None     # 6维学习画像 (从 MySQL 加载)
    # context 也是并行写入的字段 (path_agent/prefetch_agent 协同时), 用 merge_dict 合并
    context: Annotated[dict, _merge_dict_reducer] = Field(default_factory=dict)  # 对话上下文 {"topic": "...", ...}
    user_id: int = 0                        # JWT 解析的用户 ID

    # ── 输出缓冲 ──
    # agent_outputs / stream_buffer 都是并行写入字段 (qa_parallel / rc_parallel / path_parallel),
    # 必须用 reducer 接受并行节点更新
    agent_outputs: Annotated[dict, _merge_dict_reducer] = Field(default_factory=dict)  # 各 Agent 输出缓存
    stream_buffer: Annotated[str, _concat_str_reducer] = ""  # SSE 流式输出缓冲区(并行时拼接)

    # ── 教学流程 (KG-Node Teaching Flow) ──
    teaching_context: Annotated[Optional[dict], _teaching_context_reducer] = None
    # {active_path: [...], current_index: 0, completed_nodes: [...], mode: "teaching"|None, topic: "..."}

    # ── 调用链追踪 (Agent Trace) ──
    trace: Annotated[list, _concat_list_reducer] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True      # 允许 BaseMessage 等非标准类型
