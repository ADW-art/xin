'''
多agent任务调度

LangGraph 编排 Supervisor + 5 个 Agent -> 实现多轮对话的任务分发与循环处理
'''
import json #解析json
import logging #打印日志

from langgraph.graph import StateGraph, END #导入状态图，终止节点标识
from langgraph.checkpoint.memory import MemorySaver #持久记忆方案
from langchain_core.messages import HumanMessage #消息类型--用户说的话

from app.agents.state import AgentState #通用类型
from app.agents.profile_agent import profile_agent_node
from app.agents.resource_agent import resource_agent_node
from app.agents.question_agent import question_agent_node
from app.agents.path_agent import path_agent_node
from app.agents.evaluation_agent import evaluation_agent_node
from app.services.spark_client import SparkClient #向星火通信

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

#state读取当前状态--调用星火api判断意图
def supervisor_node(state: AgentState, spark: SparkClient) -> dict:
    """Supervisor 节点：分析用户意图 → 决定路由到哪个 Agent"""
    last_msg = state["messages"][-1].content if state["messages"] else ""#取最后一条，提取内容分析
    #构造请求消息
    messages = [
        {"role": "system", "content": SUPERVISOR_PROMPT},
        {"role": "user", "content": last_msg},
    ]

    try:
        raw = spark.chat_sync(messages, temperature=0.3) #返回完整回复
        result = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())#清除外套markdown
    except Exception:
        # 解析失败，默认当闲聊处理
        result = {"intent": "chat", "params": {}}

    intent = result.get("intent", "chat")  #从返回的json中取出字段，没取到就当成chat
    #意图-节点 映射
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
        "stream_buffer": "",#只判断不生成内容
    }

#构建langgraph
def build_graph(spark: SparkClient) -> StateGraph:
    """构建 LangGraph 图：Supervisor + 5 个 Agent"""
    #1.创建状态图
    workflow = StateGraph(AgentState)

    #2.在流程图中添加节点
    # Supervisor 节点，把 spark 注入进去
    workflow.add_node("supervisor" #节点名
                      , lambda s: supervisor_node(s, spark) #lambda节点函数-langgraph运行时再执行
                    )
    # 画像 Agent
    workflow.add_node("profile_agent", lambda s: profile_agent_node(s, spark))
    # 资源 Agent
    workflow.add_node("resource_agent", lambda s: resource_agent_node(s, spark))
    # 出题 Agent
    workflow.add_node("question_agent", lambda s: question_agent_node(s, spark))
    # 路径 Agent
    workflow.add_node("path_agent", lambda s: path_agent_node(s, spark))
    # 评估 Agent
    workflow.add_node("evaluation_agent", lambda s: evaluation_agent_node(s, spark))

    # 3.入口-流程从supervisor开始
    workflow.set_entry_point("supervisor")

    # 4.条件路由--根据next_agent选择路由
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

    # 6.编译流程图(添加记忆)
    return workflow.compile(checkpointer=MemorySaver())
