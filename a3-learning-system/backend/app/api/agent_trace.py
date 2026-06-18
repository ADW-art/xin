"""
AgentTrace API — 多智能体调用链追踪

提供结构化追踪数据给前端 AgentCenter 实时可视化:
  - Agent 调用顺序 (DAG)
  - 每个 Agent 的执行耗时
  - Token 消耗统计
  - 意图分类结果
"""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/agent-trace", tags=["Agent追踪"])


class TraceNode(BaseModel):
    """DAG 可视化中的单个 Agent 节点"""
    agent: str
    display_name: str
    icon: str
    duration_ms: float
    input_tokens: int
    output_tokens: int
    intent: Optional[str] = None
    input_preview: str = ""
    output_preview: str = ""
    error: Optional[str] = None


class TraceEdge(BaseModel):
    """调用链中的一条边"""
    source: str
    target: str
    relation: str = "handoff"       # handoff | return | route


class TraceResponse(BaseModel):
    """Agent 调用链完整响应"""
    thread_id: str = ""
    agents_used: list[str] = []              # 参与本次对话的 Agent 列表
    call_chain: list[TraceNode] = []         # 调用链节点 (DAG)
    edges: list[TraceEdge] = []              # 调用链边
    summary: "TraceSummary | None" = None    # 统计摘要


class TraceSummary(BaseModel):
    total_tokens: int = 0
    total_duration_ms: float = 0
    agent_count: int = 0
    llm_calls: int = 0


@router.get("/manifest")
def get_agent_manifest() -> list[dict]:
    """获取所有已注册 Agent 的前端展示清单 (无需认证)"""
    from app.agents.registry import AgentRegistry
    return AgentRegistry.get_frontend_manifest()


@router.get("/latest")
def get_latest_trace(
    thread_id: Optional[str] = Query(None, description="对话线程ID, 不传则返回最近一次"),
    current_user: User = Depends(get_current_user),
) -> TraceResponse:
    """获取指定对话的 Agent 调用链追踪数据

    AgentCenter 前端在对话进行中/结束后调用此接口,
    获取结构化的 Agent 调用链, 用于 DAG 可视化和性能统计。
    """
    from app.dependencies import get_graph
    graph = get_graph()

    resp = TraceResponse()

    if not thread_id:
        resp.thread_id = ""
        return resp

    resp.thread_id = thread_id

    try:
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = graph.get_state(config)
        if not snapshot or not snapshot.values:
            return resp

        state = snapshot.values
        trace_entries = state.get("trace", [])

        nodes = []
        edges = []
        prev_agent = "supervisor"

        for i, entry in enumerate(trace_entries):
            if not isinstance(entry, dict):
                continue

            from app.agents.registry import AgentRegistry
            agent_def = AgentRegistry.get(entry.get("agent", ""))

            nodes.append(TraceNode(
                agent=entry.get("agent", "unknown"),
                display_name=agent_def.display_name if agent_def else entry.get("agent", ""),
                icon=agent_def.icon if agent_def else "QuestionFilled",
                duration_ms=max(0, entry.get("end_ms", 0) - entry.get("start_ms", 0)),
                input_tokens=entry.get("input_tokens", 0),
                output_tokens=entry.get("output_tokens", 0),
                intent=entry.get("intent"),
                input_preview=entry.get("input_preview", "")[:100],
                output_preview=entry.get("output_preview", "")[:100],
                error=entry.get("error"),
            ))

            curr_agent = entry.get("agent", "unknown")
            edges.append(TraceEdge(
                source=prev_agent,
                target=curr_agent,
                relation="handoff" if curr_agent != "supervisor" else "return",
            ))
            prev_agent = curr_agent

        resp.call_chain = nodes
        resp.edges = edges
        resp.agents_used = list(dict.fromkeys(n.agent for n in nodes))  # 去重保序

        total_tokens = sum(n.input_tokens + n.output_tokens for n in nodes)
        total_ms = sum(n.duration_ms for n in nodes)
        resp.summary = TraceSummary(
            total_tokens=total_tokens,
            total_duration_ms=total_ms,
            agent_count=len(resp.agents_used),
            llm_calls=len([n for n in nodes if n.agent != "supervisor"]),
        )

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("AgentTrace: 获取追踪失败 - %s", e)

    return resp
