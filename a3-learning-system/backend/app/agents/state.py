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


class AgentState(BaseModel):
    """多智能体共享状态 — Pydantic v2 验证

    通过 LangGraph 图传递, 每个 Agent 节点读取/写入。
    context 和 agent_outputs 在各节点中通过 {**old, **new} 模式合并。
    """

    # ── 消息历史 (LangGraph add_messages reducer 自动合并) ──
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # ── Agent 路由 ──
    current_agent: str = "supervisor"       # 当前激活的 Agent
    next_agent: Optional[str] = None        # Supervisor 的路由决策

    # ── 用户上下文 ──
    user_profile: Optional[dict] = None     # 6维学习画像 (从 MySQL 加载)
    context: dict = Field(default_factory=dict)  # 对话上下文 {"topic": "...", ...}
    user_id: int = 0                        # JWT 解析的用户 ID

    # ── 输出缓冲 ──
    agent_outputs: dict = Field(default_factory=dict)  # 各 Agent 输出缓存
    stream_buffer: str = ""                 # SSE 流式输出缓冲区

    # ── 教学流程 (KG-Node Teaching Flow) ──
    teaching_context: Optional[dict] = None
    # {active_path: [...], current_index: 0, completed_nodes: [...], mode: "teaching"|None, topic: "..."}

    class Config:
        arbitrary_types_allowed = True      # 允许 BaseMessage 等非标准类型
