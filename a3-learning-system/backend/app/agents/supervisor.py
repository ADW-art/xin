import json
import logging

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage

from app.agents.state import AgentState
from app.services.spark_client import SparkClient

logger = logging.getLogger(__name__)

# 意图分类用到的 System Prompt
SUPERVISOR_PROMPT = """你是一个学习系统的调度中枢。根据用户输入，判断意图并返回 JSON。

意图类型及路由目标：
1. "profile" — 用户介绍自己、说学习背景/目标/时间安排/偏好 → 路由到 profile_agent
2. "resource" — 用户想学某个知识点、需要学习资料/文档/导图 → 路由到 resource_agent
3. "question" — 用户想做练习题、测试 → 路由到 question_agent
4. "path" — 用户想了解学习路线、下一步学什么 → 路由到 path_agent
5. "evaluation" — 用户想查看学习报告、评估结果 → 路由到 evaluation_agent
6. "chat" — 普通闲聊、问候、感谢 → 直接结束，不需要路由

请只返回一行 JSON，格式：{"intent": "...", "params": {"topic": "..."}}"""


def supervisor_node(state: AgentState, spark: SparkClient) -> dict:
    """Supervisor 节点：分析用户意图 → 决定路由到哪个 Agent"""
    last_msg = state["messages"][-1].content if state["messages"] else ""

    messages = [
        {"role": "system", "content": SUPERVISOR_PROMPT},
        {"role": "user", "content": last_msg},
    ]

    try:
        raw = spark.chat_sync(messages, temperature=0.3)
        result = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
    except Exception:
        # 解析失败，默认当闲聊处理
        result = {"intent": "chat", "params": {}}

    intent = result.get("intent", "chat")
    route_map = {
        "profile": "profile_agent",
        "resource": "resource_agent",
        "question": "question_agent",
        "path": "path_agent",
        "evaluation": "evaluation_agent",
        "chat": "END",
    }
    next_agent = route_map.get(intent, "END")

    logger.info("Supervisor: intent=%s → route=%s", intent, next_agent)

    return {
        "current_agent": "supervisor",
        "next_agent": next_agent,
        "context": result.get("params", {}),
        "stream_buffer": "",
    }


def _stub_agent_factory(name: str):
    """工厂函数：创建占位 Agent 节点（后续替换为真实逻辑）"""
    def _node(state: AgentState) -> dict:
        return {
            "current_agent": name,
            "stream_buffer": f"[{name}] 收到指令，正在准备响应...",
            "agent_outputs": {**state.get("agent_outputs", {}), name: "stub"},
        }
    return _node


def build_graph(spark: SparkClient) -> StateGraph:
    """构建 LangGraph 图：Supervisor + 5 个占位 Agent"""
    workflow = StateGraph(AgentState)

    # Supervisor 节点，把 spark 注入进去
    workflow.add_node("supervisor", lambda s: supervisor_node(s, spark))

    # 5 个占位 Agent 节点
    for name in ["profile_agent", "resource_agent", "question_agent", "path_agent", "evaluation_agent"]:
        workflow.add_node(name, _stub_agent_factory(name))

    # 入口
    workflow.set_entry_point("supervisor")

    # Supervisor → 根据 next_agent 值路由
    workflow.add_conditional_edges(
        "supervisor",
        lambda s: s["next_agent"],
        {
            "profile_agent": "profile_agent",
            "resource_agent": "resource_agent",
            "question_agent": "question_agent",
            "path_agent": "path_agent",
            "evaluation_agent": "evaluation_agent",
            "END": END,
        },
    )

    # 所有 Agent 执行完 → 回到 Supervisor
    for name in ["profile_agent", "resource_agent", "question_agent", "path_agent", "evaluation_agent"]:
        workflow.add_edge(name, "supervisor")

    return workflow.compile(checkpointer=MemorySaver())
