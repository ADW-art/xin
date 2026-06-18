"""
Chat Agent — 闲聊与通用回复

从 Supervisor 拆分出来，Supervisor 只做路由分类，
Chat 回复由本 Agent 独立完成。

参考: LangGraph Supervisor Pattern — 单一职责原则
"""

import re
import logging
from app.agents.state import AgentState

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """你是 A3 学习助手，一个专业的 AI 学习辅导员。你的职责是帮助学生高效学习。

回答规则（必须遵守）：
1. 直接回答用户的问题，**绝对不要重复或复述用户的问题**
2. 回答要专业、具体、有实质内容，不要说空话套话
3. 如果用户问的是学习相关话题，给出有价值的建议或解答
4. 控制在 200 字以内，简洁有力
5. 用中文回答
6. 如果用户消息似乎与之前的对话有关（如代词"它""这个"、追问、承接上文），请结合对话历史理解用户的真实意图
7. 在回答结尾，如果下方有【画像引导】提示，请按提示添加一句自然的追问；如果没有提示则不要追问，直接在结尾推荐下一步可做的学习操作"""

CHAT_PROFILE_GUIDE_INCOMPLETE = """
【画像引导】用户的学习画像还不完整，目前缺少以下维度：{empty_dims}。
请在你回复的最后一句话自然地带出一句追问，引导用户补充缺失的信息。
追问要像朋友聊天一样自然，例如：「对了，我还不了解你每周能投入多少时间学习呢，方便说一下吗？」
绝对不要用生硬的列表列出选项，也不要一次问多个维度。只挑其中一个缺失维度自然地问。"""

CHAT_PROFILE_GUIDE_COMPLETE = """
【画像引导】用户画像已完整。回复结尾可以自然地推荐下一步学习操作，例如评估、出题、规划路径等。不要追问画像相关问题。"""


def _get_profile_status(profile: dict | None) -> tuple[list[str], list[str]]:
    """分析画像填写状态，返回 (已填维度列表, 未填维度列表)"""
    ALL_DIMS = ["knowledge_base", "cognitive_style", "learning_goal",
                "weekly_hours", "preferred_resource_type", "error_patterns"]
    DIM_LABELS = {
        "knowledge_base": "知识基础", "cognitive_style": "认知风格",
        "learning_goal": "学习目标", "weekly_hours": "每周时间",
        "preferred_resource_type": "偏好资源", "error_patterns": "易错模式",
    }
    profile = profile or {}
    filled = [DIM_LABELS[k] for k in ALL_DIMS
              if k in profile and profile[k] is not None and profile[k] != ""]
    empty = [DIM_LABELS[k] for k in ALL_DIMS
             if k not in profile or profile[k] is None or profile[k] == ""]
    return filled, empty


def chat_agent_node(state: AgentState, spark) -> dict:
    """Chat Agent: 处理闲聊/问候/感谢等非学习意图的回复

    从 supervisor_node 拆分，专注回复生成，不做路由判断。
    """

    from app.core.shared_utils import _build_llm_messages

    all_messages = state.get("messages", []) if isinstance(state, dict) else state.messages
    profile = state.get("user_profile", {}) if isinstance(state, dict) else (state.user_profile or {})
    last_msg = all_messages[-1].content if all_messages else ""

    _, empty_dims = _get_profile_status(profile)

    if empty_dims:
        empty_labels = ", ".join(empty_dims)
        chat_system = CHAT_SYSTEM_PROMPT + "\n" + CHAT_PROFILE_GUIDE_INCOMPLETE.format(
            empty_dims=empty_labels)
    else:
        chat_system = CHAT_SYSTEM_PROMPT + "\n" + CHAT_PROFILE_GUIDE_COMPLETE

    chat_messages = _build_llm_messages(chat_system, all_messages, last_msg, max_history=6)

    logger.info("ChatAgent: 生成回复 (画像维度: 已填%d/未填%d)", 6 - len(empty_dims), len(empty_dims))

    return {
        "current_agent": "chat_agent",
        "next_agent": "END",
        "agent_outputs": {
            "chat_agent": {
                "stream_pending": {
                    "messages": chat_messages,
                    "temperature": 0.7,
                    "max_tokens": 512,
                    "use_safe": True,
                    "chunk_size": 2,
                }
            }
        },
    }
