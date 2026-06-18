'''
多agent任务调度

LangGraph 编排 Supervisor + 5 个 Agent -> 实现多轮对话的任务分发与循环处理
'''
import json #解析json
import re   # 正则匹配（关键词兜底）
import logging #打印日志
import os

from langgraph.graph import StateGraph, END #导入状态图，终止节点标识
from app.checkpoint_sqlite import SqliteSaver  # SQLite 持久化 checkpoint
from langchain_core.messages import HumanMessage #消息类型--用户说的话
from app.config import settings

from app.agents.state import AgentState #通用类型
from app.agents.profile_agent import profile_agent_node
from app.agents.resource_agent import resource_agent_node
from app.agents.question_agent import question_agent_node, is_answer_submission  # 答案检测
from app.agents.path_agent import path_agent_node
from app.agents.evaluation_agent import evaluation_agent_node
from app.services.spark_client import SparkClient #向星火通信

logger = logging.getLogger(__name__)

# 意图分类用到的 System Prompt
SUPERVISOR_PROMPT = """【你是纯分类器，不是回答者】
你的唯一任务是判断用户意图，返回一个 JSON 对象。
绝对禁止：解释概念、回答问题、生成题目、给出建议。只做分类。

意图类型（6选1）：
- chat: 闲聊/问候/感谢/情绪表达
- resource: 学习请求/获取知识/生成代码/生成文档/生成导图/对比分析/调试帮助
- question: 出题/做题/练习/测试/刷题/答题/提交答案
- path: 路线/计划/下一步/学什么好/学习规划/先后顺序
- evaluation: 评估/报告/水平检测/掌握情况/检查进度
- profile: 描述学习背景/基础/时间安排/偏好（不含具体学习请求的自述）

────────────────────────────────
resource 意图详细触发词分类
────────────────────────────────

【A类-概念学习】
触发词："学XX""教我XX""解释XX""什么是XX""XX的概念""XX的原理"
       "XX和YY的区别""XX vs YY""对比XX和YY""XX的优缺点"
       "为什么要用XX""XX解决了什么问题""XX的适用场景"
→ params.resource_type = "document"

【B类-代码生成与调试】
触发词："写一个XX""写段代码""写个函数""用XX实现YY""实现一个XX"
       "XX怎么写""XX如何实现""XX的代码示例""XX的语法"
       "帮我debug""这段代码错在哪""为什么报错""fix这个bug"
       "改一下这段代码""帮我优化XX""这段代码能优化吗"
→ params.resource_type = "code_example"

【C类-资料生成】
触发词："生成XX""制作XX""创建XX""画一个XX""画个XX"
       "思维导图""脑图""知识图谱""整理笔记""总结一下"
       "列一个XX""列出XX的用法""XX的API汇总""XX速查表"
→ 含"思维导图/脑图/导图/画" → params.resource_type = "mindmap"
→ 含"出题/练习题/题目" → params.resource_type = "question_set"
→ 其他 → params.resource_type = "document"

【D类-对比分析】
触发词："XX和YY的区别""XX vs YY""对比""差异""辨析""优缺点"
→ params.resource_type = "document"（生成含对比表格的文档）

────────────────────────────────
意图分类规则（严格按优先级从高到低匹配）
────────────────────────────────

1. 含"评估""报告""水平""掌握""能打几分""检查进度""学得怎样" → evaluation
2. 含"出题""做题""练习""测试""刷题""几道""题目""编程题""测一下""来一题" → question
3. 含"路线""计划""下一步""学什么""路径""规划""先后顺序""先学哪个""学到哪" → path
4. 含上述 A/B/C/D 任一类 resource 触发词 → resource
5. 描述自己学习背景/基础/时间安排/偏好，且不含具体学习请求 → profile
6. 其他 → chat

────────────────────────────────
输出格式（只输出JSON，不要任何其他文字）
────────────────────────────────

对于 resource 意图，params 必须包含 resource_type 推测和 topic：
{"intent":"resource","params":{"resource_type":"code_example","topic":"快速排序"}}

resource_type 取值: document / code_example / mindmap / question_set
- "写XX代码""XX怎么写""debug""代码示例""实现XX""写个函数" → code_example
- "思维导图""脑图""画个图""知识图谱" → mindmap
- "出题""练习题""题目" → question_set
- 其他 → document

对于其他意图，params 可为空：
{"intent":"chat","params":{}}"""

SUPERVISOR_PROFILE_CONTEXT = """
【上下文：用户画像尚未完全采集】
已采集维度：{filled_dims}
待采集维度：{empty_dims}

注意：只有当用户的消息明显是在回答画像采集问题（如描述学习基础、认知偏好、时间安排等）时，
才将意图分类为 "profile"。如果用户明确要求其他功能（评估、出题、查报告、学新知识），请优先响应用户的实际需求。"""

# Chat 回复专用 System Prompt（升级版 - 2026-06-18）
CHAT_SYSTEM_PROMPT = """你是 A3 学习助手，一个专业的 AI 学习辅导员。

回答规则（必须严格遵守）：
1. 直接回答问题，**绝对不要重复或复述用户的问题**
2. 回答简洁有料：80-200字，至少包含一个具体例子或一条可执行建议
3. 如果用户问技术概念，必须给一个最小代码示例（3-5行）+ 一句话点明核心
4. 禁止说空话套话，包括但不限于：
   - "这是一个很好的问题"（废话，直接回答）
   - "我可以帮你..."（直接帮，不要说能帮）
   - "XXX是一个复杂的话题"（别说复杂，直接讲最核心的一点）
   - "学习编程需要耐心"（用户不需要鸡汤，需要知识）
5. 禁止在开头复述用户的问题（如"你问的是装饰器的概念，装饰器是..." → 直接说"装饰器是..."）
6. 技术话题用中文解释，代码示例保留英文关键字
7. 如果用户消息含代词（"它""这个""那个""上面那个"），结合对话历史推断指代
8. 结尾：如果下方有【画像引导】提示则按提示自然追问；否则推荐下一步操作"""

# Chat 回复时注入的画像引导（运行时根据画像状态动态拼接）
CHAT_PROFILE_GUIDE_INCOMPLETE = """
【画像引导】用户的学习画像还不完整，目前缺少以下维度：{empty_dims}。
请在你回复的最后一句话自然地带出一句追问，引导用户补充缺失的信息。
追问要像朋友聊天一样自然，例如：「对了，我还不了解你每周能投入多少时间学习呢，方便说一下吗？」
绝对不要用生硬的列表列出选项，也不要一次问多个维度。只挑其中一个缺失维度自然地问。"""

CHAT_PROFILE_GUIDE_COMPLETE = """
【画像引导】用户画像已完整。回复结尾可以自然地推荐下一步学习操作，例如评估、出题、规划路径等。不要追问画像相关问题。"""


def _get_profile_status(profile: dict | None) -> tuple[list[str], list[str]]:
    """分析画像填写状态，返回 (已填维度列表, 未填维度列表)"""
    ALL_DIMS = ["knowledge_base", "cognitive_style", "learning_goal", "weekly_hours", "preferred_resource_type", "error_patterns"]
    DIM_LABELS = {
        "knowledge_base": "知识基础",
        "cognitive_style": "认知风格",
        "learning_goal": "学习目标",
        "weekly_hours": "每周时间",
        "preferred_resource_type": "偏好资源",
        "error_patterns": "易错模式",
    }
    profile = profile or {}
    filled = [DIM_LABELS[k] for k in ALL_DIMS if k in profile and profile[k] is not None and profile[k] != ""]
    empty = [DIM_LABELS[k] for k in ALL_DIMS if k not in profile or profile[k] is None or profile[k] == ""]
    return filled, empty


def _is_broad_learning_request(text: str) -> bool:
    """判断用户消息是否为广泛学习请求（需启动教学流程，而非点对点资源生成）

    排除特定问题（"XX是什么""XX和YY的区别"等），只匹配明确的"我想系统学XX"类请求。
    """
    # 先排除：含特定问题关键词的不触发教学流程
    specific_markers = [
        "是什么", "什么意思", "区别", "vs", "VS", "对比", "比较",
        "怎么用", "怎么写", "如何实现", "实现一个", "写一个", "写一段",
        "代码", "debug", "报错", "bug", "错在哪", "怎么改", "怎么做",
        "如何做", "示例", "例子", "总结", "定义", "概念",
    ]
    for mk in specific_markers:
        if mk in text:
            return False

    # 广泛学习意图关键词
    broad_markers = [
        "我想学", "我要学", "教我", "教一下", "想学", "学一下",
        "帮我学", "从零", "入门", "系统地", "系统学", "零基础",
        "初学", "刚开始学", "想系统学", "想好好学",
    ]
    for mk in broad_markers:
        if mk in text:
            return True

    # 短消息 + 含"学/学习"+"语言/学科名"（如"学Python""学C++""学算法""学前端"）
    stripped = text.strip()
    if len(stripped) <= 15 and ("学" in stripped or "学习" in stripped):
        # 必须包含具体学科名，不是"学习"单独使用
        subject_hints = [
            "Python", "Java", "C++", "Go", "Rust", "JavaScript", "TypeScript",
            "前端", "后端", "算法", "数据结构", "机器学习", "深度学习",
            "数据库", "SQL", "网络", "操作系统", "Linux", "Docker",
            "React", "Vue", "Spring", "Django", "Flask", "FastAPI",
        ]
        for subj in subject_hints:
            if subj.lower() in stripped.lower():
                return True

    return False


def _is_teaching_continue(text: str) -> bool:
    """判断用户消息是否为教学流程的继续信号"""
    stripped = text.strip()
    # 精确匹配简洁确认/继续信号（不匹配含额外内容的复合消息）
    short_continue = re.match(
        r'^(好|好的|可以|行|来|开始|没问题|嗯|OK|ok|yes|是|对|继续|下一个|下一节|接着|继续学|接着学|往下|往下学|学下一个|go on|next|continue|sure|yep|yeah|当然|必须的|搞起|来吧|开始吧|继续吧|OK吧)$',
        stripped
    )
    if short_continue:
        return True
    # 稍微长一点的确认（如"当然要继续""好的继续吧"等），但不能太长（避免误匹配）
    if len(stripped) <= 10 and any(kw in stripped for kw in ["继续", "下一个", "接着", "往下", "go on", "next"]):
        return True
    return False


def _keyword_fallback(text: str) -> dict:
    """JSON 解析失败时的关键词兜底意图分类"""
    # 优先级从高到低：具体意图 > 通用意图
    if any(k in text for k in ["评估", "报告", "水平", "掌握", "学习情况"]):
        return {"intent": "evaluation", "params": {}}
    # question: 支持多种变体（"出X道题""做X道""刷题""练习"等）
    if any(k in text for k in ["出题", "做题", "练习", "测试", "刷题", "再来一道",
                                "算法题", "编程题"]):
        return {"intent": "question", "params": {}}
    # 宽松匹配：含"道"+"题"或单独的"题目"/"几道"
    if re.search(r'\d*道.*题|题.*\d*道|几道|题目', text):
        return {"intent": "question", "params": {}}
    if any(k in text for k in ["路线", "计划", "下一步", "学什么", "接下来", "学到哪"]):
        return {"intent": "path", "params": {}}
    # profile 关键词：只匹配明确的自述（"我是XX"而非"我想学XX"是因为后者是学习请求）
    if any(k in text for k in ["我是初学者", "我零基础", "我没学过", "我是小白", "我是新手"]):
        return {"intent": "profile", "params": {}}
    if any(k in text for k in ["我有经验", "我之前", "我在做", "我从事", "我是做"]):
        return {"intent": "profile", "params": {}}
    # resource 关键词放在最后（最通用，但排除"我想学"→profile已在上面处理）
    if any(k in text for k in ["教我", "解释", "什么是", "怎么用", "教一下", "帮我学", "介绍一下",
                                "区别", "对比", "差异", "为什么", "如何", "怎么", "原理",
                                "是什么", "vs", "VS", "优缺点", "辨析",
                                "生成", "制作", "创建", "做一个", "画一个", "画个",
                                "写一个", "写一段", "写个", "给我写", "给我一个", "写个函数",
                                "给我讲", "讲一下", "讲解", "介绍", "意思", "含义",
                                "思维导图", "代码示例", "代码案例", "列一个", "列出",
                                "整理", "总结一下", "了解一下", "学一下",
                                "怎么写", "如何实现", "实现一个", "用XX实现", "debug",
                                "错在哪", "为什么报错", "fix", "报错", "bug",
                                "代码能优化", "帮我优化", "改一下代码"]):
        return {"intent": "resource", "params": {}}
    return {"intent": "chat", "params": {}}


def _proactive_suggest(last_agent: str, last_output: dict) -> dict | None:
    """根据上一轮 Agent 输出，主动推荐下一步

    返回 None 表示无主动调度（正常走 LLM 分类）
    返回 dict 表示强制路由到指定意图
    """
    # 场景: 教学完成 → 推荐练题
    if last_agent == "resource_agent":
        return {"intent": "question", "params": {}, "reason": "教学后推荐练习"}

    # 场景: 评估完成 → 推荐针对薄弱点学习
    if last_agent == "evaluation_agent":
        return {"intent": "resource", "params": {}, "reason": "评估后推荐针对性学习"}

    # 场景: 路径规划完成 → 推荐开始第一阶段
    if last_agent == "path_agent":
        return {"intent": "resource", "params": {}, "reason": "规划后推荐开始学习"}

    # 场景: 画像采集完成 → 推荐首次测试或路径规划
    if last_agent == "profile_agent":
        profile_data = last_output.get("profile_data", {})
        if profile_data and len(profile_data) >= 3:
            return {"intent": "path", "params": {}, "reason": "画像完成后推荐规划"}

    # 场景: 评阅完成(打分后) → 根据正确率推荐
    if last_agent == "question_agent":
        mode = last_output.get("mode")
        if mode == "grade":
            p_known = last_output.get("bkt_p_known", 0.5)
            if p_known >= 0.7:
                return {"intent": "resource", "params": {}, "reason": "掌握良好，推荐进阶知识"}
            else:
                return {"intent": "resource", "params": {}, "reason": "薄弱点，推荐复习基础"}

    return None


#state读取当前状态--调用星火api判断意图
def supervisor_node(state: AgentState, spark: SparkClient) -> dict:
    """Supervisor 节点：分析用户意图 → 决定路由到哪个 Agent"""
    state = dict(state)  # TypedDict → dict（确保下标访问可用）
    last_msg = state["messages"][-1].content if state["messages"] else ""#取最后一条，提取内容分析
    profile = state.get("user_profile") or {}
    all_messages = state.get("messages", [])
    agent_outputs = state.get("agent_outputs", {})
    current_agent = state.get("current_agent", "supervisor")

    # ══════════════════════════════════════
    # 优先级-1: 重入检测 —— Agent 执行完毕后决定是否链式调用
    # ══════════════════════════════════════
    if current_agent != "supervisor":
        # 教学流程链式路由: path_agent (teaching) → resource_agent
        if current_agent == "path_agent":
            path_output = agent_outputs.get("path_agent", {})
            if path_output.get("teaching_stage") in ("starting", "node_ready"):
                logger.info("Supervisor: 教学链式 path_agent → resource_agent")
                return {
                    "current_agent": "supervisor",
                    "next_agent": "resource_agent",
                    "context": path_output.get("teach_context", state.get("context", {})),
                    "stream_buffer": "",
                }
            if path_output.get("teaching_stage") == "completed":
                logger.info("Supervisor: 教学流程已完成")
                return {
                    "current_agent": "supervisor",
                    "next_agent": "END",
                    "context": state.get("context", {}),
                    "stream_buffer": "",
                }

        logger.info("Supervisor: Agent '%s' 已完成，结束当前轮次", current_agent)
        return {
            "current_agent": "supervisor",
            "next_agent": "END",
            "context": state.get("context", {}),
            "stream_buffer": "",
        }

    # ══════════════════════════════════════
    # 优先级0: 教学流程继续检测 (teaching_continue)
    # ══════════════════════════════════════
    tc = state.get("teaching_context") or {}
    if tc.get("mode") == "teaching" and _is_teaching_continue(last_msg):
        logger.info("Supervisor: 教学流程继续 → path_agent (advance index=%d)", tc.get("current_index", 0))
        return {
            "current_agent": "supervisor",
            "next_agent": "path_agent",
            "context": {"teaching_continue": True},
            "stream_buffer": "",
        }

    # ══════════════════════════════════════
    # 优先级1: 答案提交检测
    # ══════════════════════════════════════
    if is_answer_submission(last_msg):
        logger.info("Supervisor: 检测到答案提交格式 → question_agent")
        return {
            "current_agent": "supervisor",
            "next_agent": "question_agent",
            "context": {},
            "stream_buffer": "",
        }

    # ══════════════════════════════════════
    # 优先级1: 主动调度（上一轮 Agent 完成后的推荐）
    # ══════════════════════════════════════
    # 检测用户是否在"被动跟随"推荐（简短确认如"好""可以""来吧""开始"等）
    passive_confirm = re.match(r'^(好|好的|可以|行|来|开始|没问题|嗯|OK|ok|yes|是|对|继续)$', last_msg.strip())
    if passive_confirm and len(all_messages) >= 2:
        # 找到上一个非 chat 的 Agent
        for msg in reversed(all_messages[:-1]):
            prev_agent = getattr(msg, 'additional_kwargs', {}).get('agent', '')
            if prev_agent and prev_agent != 'chat':
                prev_output = agent_outputs.get(prev_agent, {})
                proactive = _proactive_suggest(prev_agent, prev_output)
                if proactive:
                    logger.info("Supervisor: 主动调度 %s → %s (原因: %s)",
                                prev_agent, proactive["intent"], proactive["reason"])
                    route_map = {
                        "profile": "profile_agent",
                        "resource": "resource_agent",
                        "question": "question_agent",
                        "path": "path_agent",
                        "evaluation": "evaluation_agent",
                    }
                    next_agent = route_map.get(proactive["intent"], "END")
                    return {
                        "current_agent": "supervisor",
                        "next_agent": next_agent,
                        "context": proactive.get("params", {}),
                        "stream_buffer": "",
                    }
                break

    # ── 构建带画像上下文的 prompt ──
    filled_dims, empty_dims = _get_profile_status(profile)
    system_prompt = SUPERVISOR_PROMPT
    if empty_dims:  # 还有未填维度 → 注入画像采集上下文（但不再强制劫持）
        system_prompt += SUPERVISOR_PROFILE_CONTEXT.format(
            filled_dims=", ".join(filled_dims) if filled_dims else "(无)",
            empty_dims=", ".join(empty_dims),
        )

    # 意图分类：携带最近对话历史（最多3轮），提供足够上下文理解代词和追问
    classify_context = []
    for msg in all_messages[-6:]:  # 最近6条消息（约3轮对话）
        content = str(getattr(msg, 'content', msg))
        msg_type = type(msg).__name__
        if 'Human' in msg_type:
            classify_context.append({"role": "user", "content": content[:300]})
        elif 'AI' in msg_type:
            classify_context.append({"role": "assistant", "content": content[:200]})
    # 确保最后一条是用户消息（当前问题），防止all_messages末尾非HumanMessage
    if not classify_context or classify_context[-1].get("role") != "user":
        classify_context.append({"role": "user", "content": last_msg})

    classify_messages = [
        {"role": "system", "content": system_prompt},
    ] + classify_context

    raw = ""
    try:
        raw = spark.chat_sync(classify_messages, temperature=0.3) #返回完整回复
        result = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())#清除外套markdown
    except Exception:
        # 解析失败 → 先尝试从 LLM 回复中提取 intent 字段
        match = re.search(r'"intent"\s*:\s*"(\w+)"', raw)
        if match:
            result = {"intent": match.group(1), "params": {}}
        else:
            # 最后兜底：关键词匹配
            result = _keyword_fallback(last_msg)

    intent = result.get("intent", "chat")

    # 关键词覆盖1：LLM 分类为 chat 时，用关键词二次校验
    if intent == "chat":
        corrected = _keyword_fallback(last_msg)
        if corrected["intent"] != "chat":
            intent = corrected["intent"]

    # 关键词覆盖2：LLM 分类为 resource 时，用关键词二次校验（resource 太通用）
    if intent == "resource":
        # 2a: 更具体的意图优先
        corrected = _keyword_fallback(last_msg)
        if corrected["intent"] not in ("resource", "chat"):
            intent = corrected["intent"]
            logger.info("LLM said resource, keyword corrected to %s", intent)
        else:
            # 2b: 检查是否像 profile
            # 注意：只匹配明确的自述句（"我是XX"不是"我想学XX"）
            profile_kw = ["我是学", "我是做", "我是计算机", "我有经验", "我学过", "我之前", "我在做"]
            # "我想学XX" → resource_agent (not profile!)
            if any(k in last_msg for k in profile_kw):
                intent = "profile"
            # 更宽松匹配：明确的初学者自述（但不包含具体的"学XX"请求）
            if any(k in last_msg for k in ["我是初学者", "我零基础", "我没学过"]) and not any(k in last_msg for k in ["学Python","学java","学C+","学算法","学数据","学机器","学前端","学后端"]):
                intent = "profile"
            if any(k in last_msg for k in profile_kw):
                intent = "profile"
                logger.info("LLM said resource, keyword corrected to %s", intent)

    route_map = {
        "profile": "profile_agent",
        "resource": "resource_agent",
        "question": "question_agent",
        "path": "path_agent",
        "evaluation": "evaluation_agent",
        "chat": "chat_agent",  # v3: chat 路由到独立 chat_agent
        "teaching_continue": "path_agent",  # 教学流程继续
    }
    next_agent = route_map.get(intent, "chat_agent")
    context_result = result.get("params", {})

    # ══════════════════════════════════════
    # 教学流程初始化: 广泛学习请求 → path_agent 构建教学序列
    # ══════════════════════════════════════
    if intent == "resource" and (not tc or not tc.get("mode")):
        if _is_broad_learning_request(last_msg):
            next_agent = "path_agent"
            context_result = dict(context_result)
            context_result["init_teaching"] = True
            logger.info("Supervisor: 广泛学习请求 → 启动教学流程 (via path_agent)")

    logger.info("Supervisor: intent=%s → route=%s", intent, next_agent)

    return {
        "current_agent": "supervisor",
        "next_agent": next_agent,
        "context": context_result,
    }

# 构建 LangGraph 图 (v3)
def build_graph(spark: SparkClient) -> StateGraph:
    """构建 LangGraph 图：Supervisor + Chat Agent + 5 Worker Agent

    v3 改动:
      - 新增 chat_agent: 处理闲聊/问候 (从 supervisor 拆分)
      - Supervisor 为纯路由器, 不再直接生成回复
      - Worker Agent → supervisor (非终端, 保留 bridge 模式)
      - Chat Agent → END (终端, 回复后结束)
    """
    from app.agents.chat_agent import chat_agent_node

    workflow = StateGraph(AgentState)

    # ── 节点注册 ──
    workflow.add_node("supervisor", lambda s: supervisor_node(s, spark))
    workflow.add_node("chat_agent", lambda s: chat_agent_node(s, spark))
    workflow.add_node("profile_agent", lambda s: profile_agent_node(s, spark))
    workflow.add_node("resource_agent", lambda s: resource_agent_node(s, spark))
    workflow.add_node("question_agent", lambda s: question_agent_node(s, spark))
    workflow.add_node("path_agent", lambda s: path_agent_node(s, spark))
    workflow.add_node("evaluation_agent", lambda s: evaluation_agent_node(s, spark))

    workflow.set_entry_point("supervisor")

    # ── Supervisor 条件路由 ──
    workflow.add_conditional_edges(
        "supervisor",
        lambda s: s["next_agent"] if isinstance(s, dict) else getattr(s, "next_agent", "END"),
        {
            "chat_agent": "chat_agent",
            "profile_agent": "profile_agent",
            "resource_agent": "resource_agent",
            "question_agent": "question_agent",
            "path_agent": "path_agent",
            "evaluation_agent": "evaluation_agent",
            "END": END,
        },
    )

    # ── Worker edges: worker → supervisor (保留 bridge 模式, 非终端) ──
    workflow.add_edge("profile_agent", "supervisor")
    workflow.add_edge("resource_agent", "supervisor")
    workflow.add_edge("question_agent", "supervisor")
    workflow.add_edge("path_agent", "supervisor")
    workflow.add_edge("evaluation_agent", "supervisor")
    # Chat Agent → END (终端: 聊天回复后直接结束)
    workflow.add_edge("chat_agent", END)

    # ── 编译 (SQLite checkpoint 持久化) ──
    db_path = settings.checkpoint_db_path
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    checkpointer = SqliteSaver(db_path=db_path)
    return workflow.compile(checkpointer=checkpointer)
