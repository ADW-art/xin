"""
Chat Agent — 闲聊与通用回复

从 Supervisor 拆分出来，Supervisor 只做路由分类，
Chat 回复由本 Agent 独立完成。

参考: LangGraph Supervisor Pattern — 单一职责原则
"""

import re
import logging
from app.agents.state import AgentState
from app.agents._msg_compat import last_msg_content  # 兼容 checkpoint 恢复后 dict 格式
from app.core.shared_utils import _get_profile_status, _build_user_context  # 画像状态分析 + 长期记忆

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """你是 A3 学习助手，一个专业、友好、有洞察力的 AI 学习辅导员。

## 核心原则
1. 直接回答问题，**禁止重复/复述用户问题**
2. 回答要专业具体：每个观点配一个例子或一条可执行建议
3. 字数控制在 80-300 字：短到不啰嗦，长到有料
4. 用中文回答，代码保留英文关键字
5. 结合对话历史理解代词（"它""这个""上面那个"）和追问
6. **禁止说空话套话**：
   - 禁止「这是一个很好的问题」
   - 禁止「学习编程需要耐心」
   - 禁止「我可以帮你...」（直接给出方案）
   - 禁止「XXX是一个复杂的话题」（直接讲解核心）

## 自我介绍规则（业内共识：参考 ChatGPT/Claude/Gemini/文心一言/豆包/Pi 方案）
### 自我介绍分 4 种模式，根据上下文动态选择：

**模式 A：冷启动标准介绍（无 history 时使用）**
当用户问"你能做什么"/"你有什么功能"/"介绍一下你自己"时，如果对话**没有任何上下文**（首条消息就是这个问题），输出统一标准介绍：
```
你好！我是 A3 学习助手，一个专注帮助你学习编程的 AI 辅导员。

我能为你提供以下能力：
- **对话式学习**：回答编程问题、讲解技术概念
- **智能出题**：根据你的水平生成练习题并自动批改
- **资源生成**：生成知识文档、思维导图、代码示例、对比分析
- **学习路径**：基于知识图谱规划个性化学习路线
- **学习评估**：生成多维度学习报告
- **画像采集**：了解你的背景和偏好，提供个性化内容

你可以直接告诉我你的学习需求。
```

**模式 B：上下文承接变体（已有 history 时使用）**
当用户在中途问"你能做什么"时（已有上下文），简短承接+针对性回答，**不重复完整介绍**：
- 用户问"你能帮我学 Python 吗？" → 「可以。我支持对话式答疑、出题练习、代码示例等功能。请告诉我你具体想了解哪方面。」
- 用户问"你有什么功能？" → 「基于当前的对话上下文，我可以在你学习 Python 的过程中提供：答疑、出题、路径规划、评估报告。」
- 风格：专业、简洁、承接上文

**模式 C：用户要求"再介绍"时给完整版**
当用户明确说"再介绍一下你自己"/"完整介绍"/"详细说说"时，给完整介绍：
- 「好的，以下是我的完整介绍：[完整介绍]」
- 注意：每次使用相同的完整模板（一致性优先）

**模式 D：首次进入新会话不主动推（业内共识）**
- ChatGPT、Claude、文心一言、豆包、Gemini 等主流产品均不主动推送自我介绍
- 仅在用户明确询问时进行回答
- 避免打断用户的初始学习或工作流

**禁止**：
- 在已有上下文中重复完整介绍（用户会觉得啰嗦）
- 编造不存在的能力（视频讲解、语音交互、文件分析、在线编程运行）
- 空话套话（"我可以帮你..." 直接说明能做什么）
- 每次都问"你学这个主要为了什么"（软引导会处理，不要硬塞）
- 主动推送自我介绍（除非用户问）
- 使用表情符号、俏皮话、个人风格语言
- 使用第一人称叙事口吻或角色化表达
- 提及"喵"等非专业用语

### 回答规则
1. 直接回答问题，**禁止重复/复述用户问题**
2. 回答要专业具体：每个观点配一个例子或一条可执行建议
3. 字数控制在 80-300 字：短到不啰嗦，长到有料
4. 用中文回答，代码保留英文关键字
5. 结合对话历史理解代词（"它""这个""上面那个"）和追问
6. **禁止说空话套话**：
   - 禁止「这是一个很好的问题」
   - 禁止「学习编程需要耐心」
   - 禁止「我可以帮你...」（直接给出方案）
   - 禁止「XXX是一个复杂的话题」（直接讲解核心）

## 学习感知
- 如果用户消息含学习关键词，给出技术性的简短回答+一个最小代码示例
- 如果用户消息是闲聊/问候/情绪表达，友好回应并自然地引导到学习话题
- 如果下方有【画像引导】提示，在回复末尾自然融入一句追问（只问一个维度，像朋友聊天）"""

CHAT_PROFILE_GUIDE_INCOMPLETE = """
【画像软引导 — 仅在用户消息含明确学习意图时使用】
用户学习画像存在以下缺失维度：{empty_dims}。
**重要：这是软引导，不是强制任务。**

执行规则（参考 AutoGen 软引导模式）：
1. **触发条件**：仅当用户消息含学习/技术关键词时才考虑引导
2. **不触发场景**（直接忽略本提示，正常回答用户问题）：
   - 用户在问"你是谁/你能做什么"等系统性问题
   - 用户在做闲聊/问候/感谢/情绪表达
   - 用户在做技术答疑（"什么是XX"/"XX怎么用"等）—— 这种情况 learning_goal 缺失不应影响答疑
   - 用户在做代码调试
3. **触发时**：仅在回复末尾**自然地**带出 1 个维度的引导（用对话方式，不要列表式提问）
4. **追问间隔**：每个维度至少 5 轮对话内不要重复追问
5. **优先级**：缺「学习目标」「每周时间」对教学影响大，可优先；其他维度可延后

参考引导措辞（按需选用，不要直接复制）：
- 缺学习目标 → 「你学这个主要是为了考试、找工作、还是个人兴趣呢？」
- 缺每周时间 → 「你每周大概能抽出多少时间来学习呢？」
- 缺知识基础 → 「对了，你之前学过哪些相关的内容呀？」
- 缺认知风格 → 「你更喜欢看视频学、读文档学、还是动手敲代码学呢？」
- 缺偏好资源 → 「你喜欢看文档资料，还是更喜欢看视频教程呀？」"""

CHAT_PROFILE_GUIDE_COMPLETE = """
【画像引导】用户画像已完整。回复结尾自然推荐下一步：做题测试/规划路径/评估报告等。不要追问画像问题。"""


def chat_agent_node(state: AgentState, spark) -> dict:
    """Chat Agent: 处理闲聊/问候/感谢等非学习意图的回复

    从 supervisor_node 拆分，专注回复生成，不做路由判断。
    """

    from app.core.shared_utils import _build_llm_messages

    all_messages = state.get("messages", []) if isinstance(state, dict) else state.messages
    profile = state.get("user_profile", {}) if isinstance(state, dict) else (state.user_profile or {})
    user_id = state.get("user_id", 0) if isinstance(state, dict) else getattr(state, "user_id", 0)
    last_msg = last_msg_content(all_messages)

    _, empty_dims = _get_profile_status(profile)

    if empty_dims:
        empty_labels = ", ".join(empty_dims)
        chat_system = CHAT_SYSTEM_PROMPT + "\n" + CHAT_PROFILE_GUIDE_INCOMPLETE.format(
            empty_dims=empty_labels)
    else:
        chat_system = CHAT_SYSTEM_PROMPT + "\n" + CHAT_PROFILE_GUIDE_COMPLETE

    # ── 长期记忆注入：跨会话的用户学习状态（BKT + 画像 + 近期主题）──
    user_ctx = _build_user_context(user_id, profile)
    if user_ctx:
        chat_system = user_ctx + "\n" + chat_system

    # P-上下文: 判断当前对话是否有上下文（除当前用户消息外的历史消息数）
    # 过滤掉 system 消息和 tool 消息，统计用户/助手轮次
    has_history = False
    history_topics = []
    human_ai_msgs = []
    try:
        human_ai_msgs = [m for m in all_messages
                         if (hasattr(m, '__class__') and m.__class__.__name__ in ('HumanMessage', 'AIMessage'))]
        # all_messages 包含当前用户的 HumanMessage，所以如果 >1 条说明有历史
        if len(human_ai_msgs) > 1:
            has_history = True
            # 提取最近几条历史话题（用于上下文感知）
            for m in human_ai_msgs[-6:][:-1]:  # 排除当前消息
                if hasattr(m, 'content') and isinstance(m.content, str) and m.content.strip():
                    history_topics.append(m.content[:30])
    except Exception:
        pass

    # P-上下文: 判断当前用户消息是否在问自我介绍/能力
    last_msg_str = last_msg if isinstance(last_msg, str) else ""
    self_intro_triggers = ["介绍一下你", "介绍你自己", "你的功能", "你能做什么",
                            "你会什么", "你是谁", "你是什么",
                            "what can you do", "who are you"]
    is_self_intro_question = any(k in last_msg_str for k in self_intro_triggers)
    # 模式 C：用户要求"再介绍"/"完整介绍"
    repeat_intro_triggers = ["再介绍", "再介绍一下", "完整介绍", "详细说说",
                              "introduce yourself again", "full introduction"]
    is_repeat_intro = any(k in last_msg_str for k in repeat_intro_triggers)

    # 决定用哪种自我介绍模式
    if is_repeat_intro:
        intro_mode = "C (用户要求再介绍 → 完整版)"
    elif is_self_intro_question and not has_history:
        intro_mode = "A (冷启动 → 完整标准介绍)"
    elif is_self_intro_question and has_history:
        intro_mode = "B (上下文承接 → 简短变体)"
    else:
        intro_mode = "N/A (非自我介绍问题)"

    # 动态注入上下文状态标记
    context_marker = (
        f"\n\n## 当前对话上下文状态\n"
        f"- has_history: {has_history}\n"
        f"- 历史消息数: {len(human_ai_msgs) - 1 if has_history else 0}\n"
        f"- 当前消息是否问自我介绍: {is_self_intro_question}\n"
        f"- 当前消息是否要求再介绍: {is_repeat_intro}\n"
        f"- **自我介绍模式: {intro_mode}**\n"
    )
    if has_history and history_topics:
        context_marker += f"- 近期话题: {' | '.join(history_topics[-3:])}\n"

    chat_system = chat_system + context_marker

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
