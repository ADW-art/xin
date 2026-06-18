"""
AgentState — 多智能体共享状态 (Pydantic v2)

升级要点:
  - TypedDict → Pydantic BaseModel: 运行时类型验证 + 默认值
  - 新增 trace: 每次 Agent 执行的追踪链
  - 新增 error/retry_count: 错误恢复与降级
  - 支持 Command-based handoff (LangGraph 2025 最佳实践)
"""

from __future__ import annotations
from typing import Optional, Annotated
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class TraceEntry(BaseModel):
    """单次 Agent 执行的追踪记录"""
    agent: str = ""                        # Agent 名称
    start_ms: float = 0                    # 开始时间戳 (ms)
    end_ms: float = 0                      # 结束时间戳 (ms)
    input_tokens: int = 0                  # 输入 Token 数
    output_tokens: int = 0                 # 输出 Token 数
    intent: Optional[str] = None           # Supervisor 分类的意图
    input_preview: str = ""               # 输入摘要 (前100字)
    output_preview: str = ""              # 输出摘要 (前100字)
    error: Optional[str] = None            # 若有错误, 错误信息

    @property
    def duration_ms(self) -> float:
        return max(0, self.end_ms - self.start_ms)


class AgentState(BaseModel):
    """多智能体共享状态 — Pydantic v2 验证

    通过 LangGraph 图传递, 每个 Agent 节点读取/写入。
    """

    # ── 消息历史 (LangGraph add_messages reducer 自动合并) ──
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # ── Agent 路由 ──
    current_agent: str = "supervisor"       # 当前激活的 Agent
    next_agent: Optional[str] = None        # Supervisor 的路由决策
    parent_agent: Optional[str] = None      # 发起调用的 Agent (用于 handoff)

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

    # ── 追踪与错误处理 (v3 新增) ──
    trace: list[TraceEntry] = Field(default_factory=list)
    error: Optional[str] = None             # 当前错误信息
    retry_count: int = 0                    # 当前 Agent 的重试次数
    max_retries: int = 2                    # 最大重试次数

    class Config:
        arbitrary_types_allowed = True      # 允许 BaseMessage 等非标准类型
