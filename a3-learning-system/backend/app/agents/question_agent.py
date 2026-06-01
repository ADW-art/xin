"""
Question Agent — 自适应出题

根据画像 + 最近知识点，动态调整难度和题型。
- 初始诊断测试：覆盖面广，难度适中
- 学习后测试：聚焦刚学的知识点
- 自适应：连续答对 2 次 → 升难度，答错 1 次 → 降难度
"""

import logging

from app.agents.state import AgentState
from app.services.spark_client import SparkClient

logger = logging.getLogger(__name__)

QUESTION_PROMPT = """你是一个自适应出题专家。根据学生的学习画像和当前学习阶段，生成合适的题目。

## 学生画像
- 知识基础：{knowledge_base}
- 认知风格：{cognitive_style}
- 当前难度：{difficulty}

## 题目主题
{topic}

## 出题要求
- 共出 3-4 道题
- 题型混合：选择题 2 道 + 填空题 1 道 + 代码题 1 道
- 难度：{difficulty}（简单/中等/较难）
- 每道题后面立刻给出答案和简短解析
- 代码题要有输入输出示例

格式：
### 第 N 题（题型）
题目内容...
A. 选项A  B. 选项B  C. 选项C  D. 选项D （如果是选择题）

> 答案：X
> 解析：..."""


def question_agent_node(state: AgentState, spark: SparkClient) -> dict:
    profile = state.get("user_profile") or {}
    context = state.get("context", {})
    topic = context.get("topic", "基础测试")
    kb = profile.get("knowledge_base", {"未评估": "未知"}) #取不到就填默认

    # 自适应难度：从 agent_outputs 里看之前答题记录
    outputs = state.get("agent_outputs", {}) 
    prev = outputs.get("question_agent", {})
    correct_streak = prev.get("correct_streak", 0)
    #难度评级
    if correct_streak >= 2:
        difficulty = "较难"
    elif prev.get("last_wrong"):
        difficulty = "简单"
    else:
        difficulty = "中等"

    #构建prompt
    messages = [{"role": "system", "content": QUESTION_PROMPT.format(
        knowledge_base=str(kb),
        cognitive_style=profile.get("cognitive_style", "未知"),
        difficulty=difficulty,
        topic=topic,
    )}]

    try:
        buffered = ""
        for chunk in spark.chat_stream(messages, temperature=0.6, max_tokens=2048):
            buffered += chunk
    except Exception as e:
        logger.error("QuestionAgent 生成失败: %s", e)
        buffered = f"出题时遇到问题：{e}"

    logger.info("QuestionAgent: 已生成题目 难度=%s", difficulty)

    return {
        "current_agent": "question_agent",
        "stream_buffer": buffered,
        "agent_outputs": {
            **outputs, #解包上次信息
            "question_agent": {"difficulty": difficulty, "topic": topic, "content": buffered},
        },
    }
