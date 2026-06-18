"""
多智能体注册中心 — 插件化 Agent 管理

参考: LangGraph Supervisor Pattern (2025) + Agent Registry 模式

使用方式:
    from app.agents.registry import AgentRegistry, AgentDefinition
    AgentRegistry.register(AgentDefinition(name="my_agent", ...))
    graph = AgentRegistry.build_graph(state_cls, checkpointer)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentDefinition:
    """Agent 注册定义 — 声明式描述一个 Agent 的元数据与行为"""

    name: str                           # 唯一标识: "profile_agent"
    display_name: str                   # 展示名: "画像采集 Agent"
    description: str                    # 功能描述
    icon: str                           # Element Plus 图标名: "UserFilled"
    node_fn: Callable                   # LangGraph 节点函数: (state) -> dict | Command
    keywords: list[str] = field(default_factory=list)  # 意图分类关键词
    priority: int = 0                   # 路由优先级(越高越优先)
    terminal: bool = False              # True = Worker 完成后直接 END, 不回到 Supervisor
    category: str = "worker"            # "supervisor" | "worker" | "system"


class AgentRegistry:
    """多智能体注册中心 — 模块级单例

    集中管理所有 Agent 的注册/查询/图构建。
    新增 Agent 只需调用 register() 一次，无需修改 supervisor.py。
    """

    _agents: dict[str, AgentDefinition] = {}
    _initialized: bool = False

    # ═══════════════════════════════════════════════════════════
    # 注册 / 查询
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def register(cls, defn: AgentDefinition) -> None:
        """注册一个 Agent。同名 Agent 后者覆盖前者。"""
        cls._agents[defn.name] = defn
        logger.info("AgentRegistry: 注册 %s (terminal=%s, priority=%d)",
                     defn.name, defn.terminal, defn.priority)

    @classmethod
    def get(cls, name: str) -> Optional[AgentDefinition]:
        """按名称获取 Agent 定义"""
        return cls._agents.get(name)

    @classmethod
    def get_all(cls, category: Optional[str] = None) -> list[AgentDefinition]:
        """获取所有已注册 Agent, 可按 category 过滤"""
        agents = list(cls._agents.values())
        if category:
            agents = [a for a in agents if a.category == category]
        return sorted(agents, key=lambda a: -a.priority)

    @classmethod
    def get_worker_agents(cls) -> list[AgentDefinition]:
        """获取所有非 Supervisor 的 Worker Agent"""
        return [a for a in cls._agents.values()
                if a.category == "worker" and a.name != "supervisor"]

    @classmethod
    def get_supervisor(cls) -> Optional[AgentDefinition]:
        """获取 Supervisor Agent"""
        for a in cls._agents.values():
            if a.category == "supervisor":
                return a
        return None

    # ═══════════════════════════════════════════════════════════
    # 图构建
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def build_graph(cls, state_cls, checkpointer) -> Any:
        """从注册表自动构建 LangGraph StateGraph

        自动处理:
          - 添加所有注册的 Agent 节点
          - Supervisor 条件路由 → Worker
          - Terminal Agent → END, 非 Terminal → Supervisor
          - 入口设为 supervisor

        Returns:
            编译后的 CompiledStateGraph
        """
        from langgraph.graph import StateGraph, END

        workflow = StateGraph(state_cls)

        # 添加所有节点
        for agent in cls._agents.values():
            workflow.add_node(agent.name, agent.node_fn)

        # 构建路由映射: {"profile_agent": "profile_agent", ..., "END": END}
        route_map: dict[str, Any] = {}
        for agent in cls.get_worker_agents():
            route_map[agent.name] = agent.name
        route_map["chat_agent"] = "chat_agent"
        route_map["END"] = END

        # Supervisor 条件路由
        workflow.add_conditional_edges(
            "supervisor",
            cls._supervisor_router,
            route_map,
        )

        # Worker edges: terminal → END, non-terminal → supervisor
        for agent in cls.get_worker_agents():
            target = END if agent.terminal else "supervisor"
            workflow.add_edge(agent.name, target)

        # Chat agent → END
        if "chat_agent" in cls._agents:
            workflow.add_edge("chat_agent", END)

        workflow.set_entry_point("supervisor")

        return workflow.compile(checkpointer=checkpointer)

    @staticmethod
    def _supervisor_router(state: Any) -> str:
        """Supervisor 路由函数 — 从 state.next_agent 读取路由决策"""
        next_agent = getattr(state, "next_agent", None)
        if not next_agent or next_agent == "END":
            return "END"
        if next_agent in AgentRegistry._agents:
            return next_agent
        # fallback: 未知 Agent → 回到 supervisor 重新决策
        logger.warning("AgentRegistry: 未知路由目标 '%s', fallback to chat_agent", next_agent)
        return "chat_agent"

    @classmethod
    def get_frontend_manifest(cls) -> list[dict]:
        """生成前端 AgentCenter 使用的 Agent 清单"""
        return [
            {
                "name": a.name,
                "displayName": a.display_name,
                "description": a.description,
                "icon": a.icon,
                "category": a.category,
                "terminal": a.terminal,
                "keywords": a.keywords[:5],
            }
            for a in cls._agents.values()
        ]
