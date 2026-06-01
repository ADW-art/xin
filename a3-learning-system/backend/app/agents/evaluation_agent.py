"""
Evaluation Agent — 学习效果评估

根据学生的答题记录和行为数据，生成多维度评估报告。
- 6 维评估：知识掌握/学习速度/薄弱环节/进步趋势/投入度/推荐策略
- 生成文本评估 + 建议
"""

import logging

from app.agents.state import AgentState
from app.services.spark_client import SparkClient

logger = logging.getLogger(__name__)

EVALUATION_PROMPT = """你是一个学习效果评估专家。根据学生的学习数据，生成多维度评估报告。

## 学生画像
{profile_summary}

## 评估维度（逐一分析）
1. **知识掌握度**：基于当前已掌握的知识点
2. **薄弱环节**：分析画像中的易错模式和知识缺漏
3. **学习风格适配**：当前的学习方式是否匹配认知风格
4. **进度评估**：基于画像和时间投入，评估学习效率
5. **改进建议**：2-3 条具体的改进建议
6. **下一步计划**：推荐接下来应该重点学什么

## 输出格式
用 Markdown 组织，每个维度一个 ### 标题，内容 2-3 句。
最后用 **总结** 收尾。

语气积极鼓励，给具体可操作的建议，不要泛泛而谈。"""


def evaluation_agent_node(state: AgentState, spark: SparkClient) -> dict:
    profile = state.get("user_profile") or {}

    parts = [
        f"- 知识基础：{profile.get('knowledge_base', '未填写')}",
        f"- 认知风格：{profile.get('cognitive_style', '未填写')}",
        f"- 学习目标：{profile.get('learning_goal', '未填写')}",
        f"- 每周投入：{profile.get('weekly_hours', '未填写')} 小时",
        f"- 易错模式：{profile.get('error_patterns', '未填写')}",
        f"- 偏好资源：{profile.get('preferred_resource_type', '未填写')}",
    ]
    profile_summary = "\n".join(parts) #把列表的每个元素用分隔符连成字符串

    messages = [{"role": "system", "content": EVALUATION_PROMPT.format(profile_summary=profile_summary)}]

    try:
        buffered = ""
        for chunk in spark.chat_stream(messages, temperature=0.6, max_tokens=2048):
            buffered += chunk
    except Exception as e:
        logger.error("EvaluationAgent 生成失败: %s", e)
        buffered = f"评估时遇到问题：{e}"

    logger.info("EvaluationAgent: 已生成评估报告")

    return {
        "current_agent": "evaluation_agent",
        "stream_buffer": buffered,
        "agent_outputs": {**state.get("agent_outputs", {}), "evaluation_agent": {"content": buffered}},
    }
