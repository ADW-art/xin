"""
Chat Agent — 闲聊与通用回复

从 Supervisor 拆分出来，Supervisor 只做路由分类，
Chat 回复由本 Agent 独立完成。

参考: LangGraph Supervisor Pattern — 单一职责原则
"""

import re
import logging
from app.agents.state import AgentState
from app.core.shared_utils import _get_profile_status  # 画像状态分析（与 supervisor 共享）

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """你是 A3 学习助手，一个专业、友好、有洞察力的 AI 学习辅导员。

## 核心原则
1. 直接回答问题，**禁止重复/复述用户问题**
2. 回答要专业具体：每个观点配一个例子或一条可执行建议
3. 字数控制在 80-300 字：短到不啰嗦，长到有料
4. 用中文回答，代码保留英文关键字
5. 结合对话历史理解代词（"它""这个""上面那个"）和追问
6. **禁止说空话套话**：
   - 禁止「这是一个很好的问题」（废话）
   - 禁止「学习编程需要耐心」（鸡汤）
   - 禁止「我可以帮你...」（直接帮，不要说能帮）
   - 禁止「XXX是一个复杂的话题」（直接讲核心）

## 自我介绍规则（当用户问"你能做什么"/"你有什么功能"时）
你必须严格按照以下真实功能回答，**禁止编造不存在的能力**：
- [支持] 对话式学习：回答编程问题，讲解技术概念
- [支持] 智能出题：根据你的水平生成练习题并批改
- [支持] 资源生成：生成知识文档、思维导图、代码示例、对比分析
- [支持] 学习路径：基于知识图谱规划个性化学习路线
- [支持] 学习评估：生成多维度学习报告
- [支持] 画像采集：了解你的背景和偏好，提供个性化内容
- [禁止] 说：支持视频讲解、支持语音交互、支持文件上传分析、支持在线编程运行
- [禁止] 说：连接了XX知识库、收录了XX本书（除非你确信知识库已注入）

## 学习感知
- 如果用户消息含学习关键词，给出技术性的简短回答+一个最小代码示例
- 如果用户消息是闲聊/问候/情绪表达，友好回应并自然地引导到学习话题
- 如果下方有【画像引导】提示，在回复末尾自然融入一句追问（只问一个维度，像朋友聊天）"""

CHAT_PROFILE_GUIDE_INCOMPLETE = """
【画像引导 — 必须执行】用户学习画像缺失：{empty_dims}。
**这是强制性任务**：你必须在回复末尾自然地带出一句追问，引导用户补充缺失的画像信息。
- 只挑一个缺失维度，像朋友聊天一样自然地提问
- 推荐提问示例（根据缺失维度选择）：
  · 缺知识基础 → 「对了，你之前学过哪些编程语言或相关内容呀？」
  · 缺学习目标 → 「你学这个主要是为了考试、找工作、还是个人兴趣呢？」
  · 缺每周时间 → 「你每周大概能抽出多少时间来学习呢？」
  · 缺认知风格 → 「你更喜欢看视频学、读文档学、还是动手敲代码学呢？」
  · 缺偏好资源 → 「你喜欢看文档资料，还是更喜欢看视频教程呀？」
- 禁止：一次问多个维度、用列表列出选项、语气生硬、忘记提问"""

CHAT_PROFILE_GUIDE_COMPLETE = """
【画像引导】用户画像已完整。回复结尾自然推荐下一步：做题测试/规划路径/评估报告等。不要追问画像问题。"""


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

    chat_messages = _build_llm_messages(chat_system, all_messages, last_msg, max_history=12)

    logger.info("ChatAgent: 生成回复 (画像维度: 已填%d/未填%d)", 6 - len(empty_dims), len(empty_dims))

    return {
        "current_agent": "chat_agent",
        "next_agent": "END",
        "agent_outputs": {
            "chat_agent": {
                "stream_pending": {
                    "messages": chat_messages,
                    "temperature": 0.7,
                    "max_tokens": 1024,
                    "use_safe": True,
                    "chunk_size": 2,
                }
            }
        },
    }
