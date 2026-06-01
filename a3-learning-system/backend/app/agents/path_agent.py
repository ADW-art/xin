"""
Path Agent — 学习路径规划

根据学生画像和知识图谱，规划最优学习路线。
- 拓扑排序：前置知识先学
- 难度递增：从基础到进阶
- 时间估算：考虑每周投入时间
- 复习节点：遗忘曲线复习点
"""

import logging

from app.agents.state import AgentState
from app.services.spark_client import SparkClient

logger = logging.getLogger(__name__)

PATH_PROMPT = """你是一个学习路径规划专家。根据学生的学习画像，规划最优学习路线。

## 学生画像
- 知识基础：{knowledge_base}
- 学习目标：{learning_goal}
- 每周可投入：{weekly_hours} 小时

## 当前需求
{topic}

## 规划要求
生成一份分阶段的学习路径（Markdown 格式）：

1. **当前阶段**：学生当前的知识水平分析
2. **学习路线**（用有序列表）：
   - 每个阶段标注：主题名、建议学习时长、关键知识点
   - 从基础到进阶递进
   - 前置知识排在前面
3. **时间估算**：基于每周 {weekly_hours} 小时，预计需要几周
4. **复习节点**：在遗忘曲线关键点（第 1/3/7/14 天）标注复习提醒
5. **里程碑**：阶段性的检验目标

格式清晰，用 Markdown 标题和列表组织。"""


def path_agent_node(state: AgentState, spark: SparkClient) -> dict:

    profile = state.get("user_profile") or {}
    context = state.get("context", {})
    topic = context.get("topic", state["messages"][-1].content if state["messages"] else "构建学习计划")
    kb = profile.get("knowledge_base", {"未评估": "未知"})
    weekly = profile.get("weekly_hours", "不确定")

    messages = [{"role": "system", "content": PATH_PROMPT.format( #对应插槽填入信息
        knowledge_base=str(kb),
        learning_goal=profile.get("learning_goal", "技能提升"),
        weekly_hours=weekly,
        topic=topic,
    )}]

    try:
        buffered = ""
        for chunk in spark.chat_stream(messages, temperature=0.6, max_tokens=2048):
            buffered += chunk
    except Exception as e:
        logger.error("PathAgent 生成失败: %s", e)
        buffered = f"规划路径时遇到问题：{e}"

    logger.info("PathAgent: 已生成学习路径")

    return {
        "current_agent": "path_agent",
        "stream_buffer": buffered,
        "agent_outputs": {**state.get("agent_outputs", {}), "path_agent": {"content": buffered, "topic": topic}},
    }
