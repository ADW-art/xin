"""
Resource Agent — 根据用户画像 + 当前知识点生成个性化学习资源

资源类型：
1. document      → 结构化知识文档
2. mindmap       → Markdown 标题层级（前端 markmap 渲染为导图）
3. question_set  → 3-5 道练习题，含答案解析
4. code_example  → 可执行代码案例
5. video_script  → 5 分钟讲解脚本
"""

import json
import logging

from app.agents.state import AgentState
from app.services.spark_client import SparkClient

logger = logging.getLogger(__name__)

#英文key转化为中文
TYPE_LABELS = {
    "document": "知识文档",
    "mindmap": "思维导图",
    "question_set": "练习题",
    "code_example": "代码案例",
    "video_script": "讲解脚本",
}
#核心prompt模板
RESOURCE_PROMPT = """你是一个个性化学习资源生成专家。根据学生的学习画像和当前需求，生成高质量的学习材料。

## 学生画像
{profile_text}

## 当前学习需求
{topic}

## 要生成的资源类型：{type_label}
{type_guide}

## 输出要求
- 返回纯 Markdown，不要套 ```markdown 外壳
- 内容难度匹配学生的知识基础
- 风格匹配学生的认知风格和资源偏好
- 如果有代码，写 Python 并加上注释
- 如果学生是视觉型，多用文字描述图表结构"""

TYPE_GUIDES = {
    "document": """生成一份结构化的知识文档：
- 先给一个简要概述（2-3 句）
- 分点讲解核心概念
- 配合示例说明
- 最后给一个小结""",
    "mindmap": """生成 Markdown 标题结构，前端会转为思维导图。
格式要求：用 # ## ### 层级表示主题→子主题→细节。
- # 为根节点（主题名）
- ## 为核心概念
- ### 为细节/示例
- 控制在 15-30 个节点""",
    "question_set": """生成 3-5 道练习题：
- 题型混合：选择题 + 填空题
- 每题包含：题目、选项（选择题）、答案、简短解析
- 难度从基础到进阶递进""",
    "code_example": """生成一个可运行的 Python 代码案例：
- 先写一段注释说明代码要演示什么
- 代码要有清晰的变量名和注释
- 最后给出预期输出""",
    "video_script": """生成一份 5 分钟讲解脚本：
- 时间线：0:00 开场 → 1:30 核心概念 → 3:30 实例演示 → 4:30 总结
- 每段标注时间戳和画面描述
- 语言口语化，适合朗读""",
}


def resource_agent_node(state: AgentState, spark: SparkClient) -> dict:
    """资源生成 Agent 的主逻辑"""
    profile = state.get("user_profile") or {}
    context = state.get("context", {})
    topic = context.get("topic", state["messages"][-1].content if state["messages"] else "")

    # 从画像中提取关键信息 → 拼进 Prompt
    profile_lines = [] #只拼接有值的
    if profile.get("knowledge_base"):
        profile_lines.append(f"知识基础：{profile['knowledge_base']}")
    if profile.get("cognitive_style"):
        profile_lines.append(f"认知风格：{profile['cognitive_style']}")
    if profile.get("learning_goal"):
        profile_lines.append(f"学习目标：{profile['learning_goal']}")
    if profile.get("preferred_resource_type"):
        profile_lines.append(f"偏好资源类型：{profile['preferred_resource_type']}")

    profile_text = "\n".join(profile_lines) if profile_lines else "暂无画像信息，按通用方式生成"
    #"\n".join-->把列表的每个元素用\n连接成一个字符串

    # 根据画像偏好决定资源类型，默认生成文档
    pref = profile.get("preferred_resource_type", "text")
    pref_map = {"video": "video_script", "code": "code_example", "text": "document", "interactive": "question_set"}
    resource_type = pref_map.get(pref, "document")

    type_label = TYPE_LABELS.get(resource_type, "学习资源")

    messages = [
        #传入prompt，导入画像数据
        {"role": "system", "content": RESOURCE_PROMPT.format(
            profile_text=profile_text,
            topic=topic,
            type_label=type_label,
            type_guide=TYPE_GUIDES[resource_type], #选取其中的类型
        )},
    ]

    #调用api流式生成
    try:
        buffered = ""
        for chunk in spark.chat_stream(messages, temperature=0.7, max_tokens=2048): #不同任务不同温度
            buffered += chunk #拼接
    except Exception as e:
        logger.error("ResourceAgent: 生成失败: %s", e)
        buffered = f"生成资源时遇到问题：{e}"

    logger.info("ResourceAgent: 已生成 %s，长度 %d", resource_type, len(buffered))

    return {
        "current_agent": "resource_agent",
        "stream_buffer": buffered,
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "resource_agent": {"type": resource_type, "content": buffered, "topic": topic},
            #资源类型-完整内容-知识点
        },
    }
