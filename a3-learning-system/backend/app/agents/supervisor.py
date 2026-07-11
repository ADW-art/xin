'''
多agent任务调度

LangGraph 编排 Supervisor + 5 个 Agent -> 实现多轮对话的任务分发与循环处理
'''
import json #解析json
import re   # 正则匹配（关键词兜底）
import logging #打印日志
import os
import time  # trace timing

from langgraph.graph import StateGraph, END #导入状态图，终止节点标识
from app.checkpoint_sqlite import SqliteSaver  # SQLite 持久化 checkpoint
from app.config import settings

from app.agents.state import AgentState #通用类型
from app.core.shared_utils import _get_profile_status, is_teaching_continue, resolve_teaching_reference  # 画像状态 + 教学继续检测
from app.agents.profile_agent import profile_agent_node
from app.agents.resource_agent import resource_agent_node
from app.agents.question_agent import question_agent_node, is_answer_submission  # 答案检测
from app.agents.path_agent import path_agent_node
from app.agents.evaluation_agent import evaluation_agent_node
from app.agents.collaboration import _quality_review_node, qa_join_node, rc_join_node, path_join_node, _prefetch_resource_meta
from app.agents._msg_compat import last_msg_content  # 兼容 checkpoint 恢复后 dict 格式
from langgraph.types import Send
from app.services.spark_client import SparkClient #向星火通信

logger = logging.getLogger(__name__)

# 如果设置为 True，使用 registry.py 的 AgentRegistry.build_graph() 替代手动构建
# 默认 False 保持现有行为
# 意图分类用到的 System Prompt
SUPERVISOR_PROMPT = """【你是纯分类器，不是回答者】
你的唯一任务是判断用户意图，返回一个 JSON 对象。
绝对禁止：解释概念、回答问题、生成题目、给出建议。只做分类。
Support both Chinese and English input.

意图类型（6选1）：
- chat: 闲聊/问候/感谢/情绪表达 | casual chat/greeting/thanks/emotions
- resource: 学习请求/获取知识/生成代码/生成文档/生成导图/对比分析/调试帮助 | learn/explain/teach/generate code/debug/difference between
- question: 出题/做题/练习/测试/刷题/答题/提交答案 | generate questions/exercises/quiz/practice problems/coding problems
- path: 路线/计划/下一步/学什么好/学习规划/先后顺序 | learning path/roadmap/plan/what to learn next/study plan
- evaluation: 评估/报告/水平检测/掌握情况/检查进度 | evaluate/assess/report/check progress/how am I doing
- profile: 描述学习背景/基础/时间安排/偏好（不含具体学习请求的自述）| describe background/experience/learning preferences (not specific learning requests)

────────────────────────────────
resource 意图详细触发词分类 (Detailed resource triggers)
────────────────────────────────

【A类-概念学习 Concept Learning】
    # reading_material intent - A3 extension reading requirement
    if any(k in text for k in ["推荐阅读", "拓展阅读", "推荐资料", "拓展资料", "扩展阅读", "阅读材料", "推荐文章", "推荐书", "推荐书籍", "延伸阅读", "进一步阅读", "further reading", "reading list", "recommended reading"]):
        return "{"intent": "resource", "params": {"resource_type": "reading_material", "topic": text[:200]}}"

	触发词(CN): "讲讲""讲一下""讲解""教""教我""说说""介绍"
	       "学XX""教我XX""解释XX""什么是XX""XX的概念""XX的原理"
	       "XX和YY的区别""XX vs YY""对比XX和YY""XX的优缺点"
	       "为什么要用XX""XX解决了什么问题""XX的适用场景"
	       "基础知识""基础语法""基本概念""基本用法""快速入门"
	       "巩固""复习""入门""学习""我想学""怎么学""入门教程"
	触发词(EN): "teach me""explain""what is""how does""how to""tell me about"
	       "difference between""vs""compare""pros and cons""why use"
	       "show me how""I want to learn""I want to understand"
	       "tutorial""introduction""basics""fundamentals""overview"
	       "review""consolidate""reinforce""learn about"
→ params.resource_type = "document"

【B类-代码生成与调试 Code Generation & Debugging】
触发词(CN): "写一个XX""写段代码""写个函数""用XX实现YY""实现一个XX"
       "XX怎么写""XX如何实现""XX的代码示例""XX的语法"
       "帮我debug""这段代码错在哪""为什么报错""fix这个bug"
       "改一下这段代码""帮我优化XX""这段代码能优化吗"
触发词(EN): "write a""write code""implement""code example""how to code"
       "debug""fix this""why does this error""bug""error"
       "optimize""refactor""code snippet""show me the code"
→ params.resource_type = "code_example"

【C类-资料生成 Content Generation】
触发词(CN): "生成XX""制作XX""创建XX""画一个XX""画个XX"
       "思维导图""脑图""知识图谱""整理笔记""总结一下"
       "列一个XX""列出XX的用法""XX的API汇总""XX速查表"
触发词(EN): "generate""create""make a""mindmap""mind map""summary"
       "cheatsheet""cheat sheet""list out""overview""outline"
→ 含"思维导图/脑图/导图/画/mindmap/mind map" → params.resource_type = "mindmap"
→ 含"出题/练习题/题目/exercise/question/generate problem" → params.resource_type = "question_set"
→ 其他 → params.resource_type = "document"

【D类-对比分析 Comparison】
触发词(CN): "XX和YY的区别""XX vs YY""对比""差异""辨析""优缺点"
触发词(EN): "difference between""vs""compare""comparison""pros and cons""trade off"
→ params.resource_type = "document"（生成含对比表格的文档）

────────────────────────────────
意图分类规则 Intent Classification Rules (strict priority order)
────────────────────────────────

1. 含"评估"/"报告"/"水平"/"掌握"/"evaluate"/"assess"/"report"/"check my"/"how am I"/"progress" → evaluation
2. 含"出题"/"做题"/"练习"/"测试"/"题目"/"generate question"/"give me problem"/"quiz"/"exercise"/"coding problem"/"algorithm problem" → question
   ⚠️ 关键区分: "写一个XX代码/代码示例" → resource (code_example), 不是 question
   ⚠️ "explain/teach me/what is" → resource, 不是 question
   ⚠️ question 只匹配: 出题测试/quiz/练习/exercise/practice problem
3. 含"路线"/"计划"/"下一步"/"路径"/"规划"/"roadmap"/"learning path"/"what next"/"what should I learn"/"study plan"/"path" → path
4. 含上述 A/B/C/D 任一类 resource 触发词(CN or EN) → resource
5. 描述自己学习背景/基础/时间安排/偏好(不含具体学习请求) | "I am a""I have experience""I'm a beginner""my background" → profile
6. 其他 → chat

────────────────────────────────
输出格式 Output Format (只输出JSON，不要任何其他文字)
────────────────────────────────

对于 resource 意图，params 必须包含 resource_type 推测和 topic：
{"intent":"resource","params":{"resource_type":"code_example","topic":"快速排序"}}

resource_type 取值: document / code_example / mindmap / question_set / reading_material / diagram / video_script / smart_tutoring
- "写XX代码""XX怎么写""debug""代码示例""write code""implement""code example" → code_example
- "思维导图""脑图""画个图""mindmap""mind map" → mindmap
- "推荐阅读""拓展阅读""阅读材料""further reading""reading list" → reading_material
- "图解""画图""示意图""流程图""时序图""diagram""chart" → diagram
- "完整讲解""图文视频""讲透""三合一""综合讲解""smart tutoring" → smart_tutoring
- "视频讲解""生成视频""视频脚本""video script""slideshow" → video_script
- 其他 → document
- "出题""练习题""题目""generate questions""exercises" → question_set
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

## 第一铁律：回复长度（违反即为废品，排在一切规则之前）
你的回复必须严格控制在 **80-200 字**（约3-6句话）。
- 绝对禁止超过 300 字 — 超过300字意味着你在编造废话，不是在回答问题
- 如果你发现自己写了超过5句话，立即检查是否在讲废话，删除多余的
- 一条消息只回答一个问题，只给一个例子，只推一个下一步
- 如果对方问题太宽泛（如"python""教我编程"），用一句话反问澄清，不要写教程
- **禁止输出列表/步骤/阶段/计划** — 这些需要 profile_agent / resource_agent / path_agent 处理。如果用户需要计划或教程，引导他们去找对应的Agent

## 反幻觉铁律（违反即为不合格）
1. 禁止编造技术事实 — 如果不确定某个API/语法/概念是否存在，明确说"我对此不确定"
2. 禁止猜测代码输出 — 不要写"# 输出：XXX"注释猜测结果，必须用独立代码块展示
3. 禁止凭空推荐 — 不推荐不存在的书籍/课程/网站，如果推荐必须有可靠来源
4. 禁止空洞安慰 — 不说"别担心""加油""你很棒"等无信息量的话

## 图解指令
当用户要求图解/图表/流程图/关系图解释时：
- 使用 ```mermaid 代码块生成对应图表
- 图表后紧跟1-2句文字解读

回答规则（必须严格遵守）：
1. 直接回答问题，绝对不要重复或复述用户的问题
2. 如果用户问技术概念，必须给一个最小代码示例（3-5行）+ 一句话点明核心
3. 禁止说空话套话："这是一个很好的问题""我可以帮你...""XXX是一个复杂的话题"
4. 禁止在开头复述用户的问题
5. 如果用户消息含代词（"它""这个""那个"），结合对话历史推断指代
6. 结尾：如果下方有【画像引导】提示则按提示自然追问；否则推荐下一步操作
7. 技术话题用中文解释，代码示例保留英文关键字"""

# Chat 回复时注入的画像引导（运行时根据画像状态动态拼接）
CHAT_PROFILE_GUIDE_INCOMPLETE = """
【画像引导】用户的学习画像还不完整，目前缺少以下维度：{empty_dims}。
请在你回复的最后一句话自然地带出一句追问，引导用户补充缺失的信息。
追问要像朋友聊天一样自然，例如：「对了，我还不了解你每周能投入多少时间学习呢，方便说一下吗？」
绝对不要用生硬的列表列出选项，也不要一次问多个维度。只挑其中一个缺失维度自然地问。"""

CHAT_PROFILE_GUIDE_COMPLETE = """
【画像引导】用户画像已完整。回复结尾可以自然地推荐下一步学习操作，例如评估、出题、规划路径等。不要追问画像相关问题。"""


def _is_broad_learning_request(text: str) -> bool:
    """判断用户消息是否为广泛学习请求（需启动教学流程，而非点对点资源生成）
    支持中英双语
    """
    text_lower = text.lower().strip()

    # 先排除：含特定问题关键词的不触发教学流程
    specific_markers = [
        "是什么", "什么意思", "区别", "vs", "VS", "对比", "比较",
        "怎么用", "怎么写", "如何实现", "实现一个", "写一个", "写一段",
        "代码", "debug", "报错", "bug", "错在哪", "怎么改", "怎么做",
        "如何做", "示例", "例子", "总结", "定义", "概念",
        # EN specific markers
        "what is", "difference between", "how to", "how do i",
        "write a", "implement", "debug", "bug", "error",
        "example", "tutorial on", "explain",
        # 计划/规划类请求 — 用户要的是计划展示，不是自动教学
        "制定", "计划", "规划", "学习路线", "路线图", "安排",
    ]
    for mk in specific_markers:
        if mk in text_lower:
            return False

    # 广泛学习意图关键词
    broad_markers = [
        "我想学", "我要学", "教我", "教一下", "想学", "学一下",
        "帮我学", "从零", "入门", "系统地", "系统学", "零基础",
        "初学", "刚开始学", "想系统学", "想好好学",
        # EN broad markers
        "i want to learn", "teach me", "i want to study",
        "from scratch", "beginner", "i'm new to",
        "start learning", "learn from", "get started",
    ]
    for mk in broad_markers:
        if mk in text_lower:
            return True

    # 短消息: 要求含显式学习动词 + 学科名才触发教学流程
    stripped = text.strip()
    if len(stripped) <= 30:
        has_learning_verb = any(v in text_lower for v in ["学", "学一下", "教我", "learn", "teach", "study"])
        if not has_learning_verb:
            return False  # 单学科名无学习意图 → 不触发教学
        subject_hints = [
            "Python", "Java", "C++", "Go", "Rust", "JavaScript", "TypeScript",
            "前端", "后端", "算法", "数据结构", "机器学习", "深度学习",
            "数据库", "SQL", "网络", "操作系统", "Linux", "Docker",
            "React", "Vue", "Spring", "Django", "Flask", "FastAPI",
        ]
        for subj in subject_hints:
            if subj.lower() in text_lower:
                return True

    return False


def _has_explicit_new_intent(text: str, text_lower: str) -> bool:
    """检测用户是否发起了新的明确意图（应覆盖当前教学流）

    当用户的消息明显是一个新的学习请求/评估/规划时，
    教学流的 continue 不应该劫持它。
    """
    _new_intent_signals = [
        # 学习规划意图 → 应路由 path_agent
        "学习计划", "学习路线", "规划", "计划", "安排", "学习路径",
        "roadmap", "study plan", "learning path",
        # 评估意图 → 应路由 evaluation_agent
        "评估", "报告", "检测水平", "掌握情况",
        "评估一下", "evaluate", "assess", "progress",
        # 出题意图 → 应路由 question_agent
        "出题", "测试一下", "练习", "来几道", "quiz",
        # 明确的主题学习请求（非"继续"类模糊确认）
        "帮我制定", "帮我规划", "帮我学", "教我",
        "我想学", "我要学", "讲一下", "讲讲", "解释一下",
        "说一下", "介绍下", "说说", "给我讲",
    ]
    return any(kw in text_lower for kw in _new_intent_signals)


    return True

def _keyword_fallback(text: str) -> dict:
    """JSON 解析失败时的关键词兜底意图分类 (中英双语)"""
    text_lower = text.lower()
    # 优先级从高到低：具体意图 > 通用意图

    # ── Negation detection: 否定意图 → chat（例: "我不想做计划" 不应路由到 path）──
    _negation_markers = ["不想", "不需要", "不要", "不用", "没想", "别给我", "别"]
    _is_negated = any(text.startswith(n) or n in text[:10] for n in _negation_markers)
    if _is_negated:
        return {"intent": "chat", "params": {}}  # 否定意图交给 chat_agent 处理

    # ── evaluation: 评估/报告 ──
    if any(k in text for k in ["评估", "报告", "水平", "掌握", "学习情况",
                                "evaluate", "assess", "how am i", "check my",
                                "my progress", "report on"]):
        return {"intent": "evaluation", "params": {}}

    # ── question: 出题/做题/练习 (only explicit test/quiz requests) ──
    # 高优先级：显式的出题/练习请求（不依赖 "给我" 这类泛词）
    if any(k in text for k in ["出题", "做题", "测试", "刷题", "再来一道",
                                "算法题", "编程题", "考考我", "考我",
                                "给我练", "给我出", "给我做几道", "给我刷",
                                "练习题", "考试", "测验", "考核",
                                "考一考", "考一考我",
                                "generate question", "give me a problem",
                                "give me an algorithm",
                                "quiz me", "test me", "practice problem",
                                "algorithm problem", "give me exercises",
                                "give me questions"]):
        return {"intent": "question", "params": {}}
    # 宽松匹配：含"道"+"题"或单独的"题目"/"几道"
    if re.search(r'\d*道.*题|题.*\d*道|几道|题目', text):
        return {"intent": "question", "params": {}}
    # EN: explicit exercise/quiz requests (NOT general "write/explain" requests)
    # Allow intervening words between number and type: "give me 3 Python basic exercises"
    if re.search(r'(?:give|generate|create|make)\s+me\s+(?:\d+\s+)?(?:\w+\s+){0,5}(?:problems?|questions?|exercises?|challenges?|quiz(?:zes)?)', text_lower):
        return {"intent": "question", "params": {}}

    # ── path: 路线/计划/下一步 ──
    if any(k in text for k in ["路线", "计划", "下一步", "学什么", "接下来", "学到哪",
                                "roadmap", "learning path", "what next",
                                "what should i learn", "study plan",
                                "learning plan"]):
        return {"intent": "path", "params": {}}

    # ── profile: 自述背景/经验 ──
    if any(k in text for k in ["我是初学者", "我零基础", "我没学过", "我是小白", "我是新手",
                                "我有经验", "我之前", "我在做", "我从事", "我是做",
                                "我工作了", "我工作过", "我做过", "我做了", "我学的", "我学的专业",
                                "我专业是", "我目前在做", "我目前是", "我做过后端",
                                "我做过程序员", "我是程序员", "我是工程师", "我是开发",
                                "我是学生", "我是研究生", "我是大学生", "我在读",
                                "i am a beginner", "i have experience",
                                "i'm a student", "i am a student",
                                "my background", "i work as", "i'm a",
                                "我是一位", "我是一名", "我是做后端", "我是做前端",
                                "我做后端", "我做前端", "我做全栈", "我做运维", "我做测试",
                                "我是后端", "我是前端", "我是全栈", "我是运维", "我是测试"]):
        return {"intent": "profile", "params": {}}

    # ── chat: 系统相关/自我介绍 (优先于resource，避免"介绍一下你"被误分类) ──
    if any(k in text for k in ["介绍一下你", "介绍你自己", "你的功能", "你能做什么",
                                "你会什么", "你是谁", "你是什么",
                                "what can you do", "who are you"]):
        return {"intent": "chat", "params": {}}

    # ── resource: 学习请求 (放最后，最通用) ──
    # P2-01: 区分 explain（讲解类→resource_agent）和 generate（生成类→collaborative_resource）
    _cn_explain = any(k in text for k in ["教我", "解释", "什么是", "怎么用", "教一下", "帮我学",
                             "我想学", "我要学", "想学", "学一下",
                             "区别", "对比", "差异", "为什么", "如何", "怎么", "原理",
                             "是什么", "vs", "VS", "优缺点", "辨析",
                             "讲一下", "讲解", "介绍", "意思", "含义", "给我讲",
                             "讲讲", "说说", "介绍一下",
                             "整理", "总结一下", "了解一下",
                             "debug", "错在哪", "为什么报错", "fix", "报错", "bug",
                             "代码能优化", "帮我优化", "改一下代码"])
    _cn_generate = any(k in text for k in ["生成", "制作", "创建", "做一个", "画一个", "画个", "图解", "图",
                              "写一个", "写一段", "写个", "给我写", "给我一个", "写个函数",
                              "思维导图", "流程图", "代码示例", "代码案例", "列一个", "列出",
                              "怎么写", "如何实现", "实现一个", "用XX实现"])
    _en_explain = any(k in text_lower for k in ["teach me", "explain", "what is", "how does",
                                   "how to", "tell me about", "difference between",
                                   "compare", "how do i", "show me", "i want to learn",
                                   "i want to understand", "tutorial", "debug", "fix this",
                                   "why does this"])
    _en_generate = any(k in text_lower for k in ["write a", "write code", "implement",
                                    "code example", "generate", "create",
                                    "mindmap", "mind map", "diagram", "chart", "cheatsheet"])

    if _cn_explain or _cn_generate or _en_explain or _en_generate:
        params = {}
        # P2-01: 标记 mode — generate 走协作, explain 走直接
        if _cn_generate or _en_generate:
            params["mode"] = "generate"
            logger.info("Supervisor: keyword resource mode=generate → collaborative_resource")
        else:
            params["mode"] = "explain"
            logger.info("Supervisor: keyword resource mode=explain → resource_agent")
        # Detect resource_type from keywords
        if any(k in text for k in ["代码", "debug", "报错", "bug", "error", "写一个", "写段代码",
                                     "写个函数", "实现", "fix", "怎么写", "如何实现",
                                     "代码示例", "代码案例", "代码能优化", "帮我优化", "改一下代码"]):
            params["resource_type"] = "code_example"
        elif any(k in text for k in ["思维导图", "脑图", "导图", "mindmap"]):
            params["resource_type"] = "mindmap"
        elif any(k in text for k in ["图解", "画图", "示意图", "图示", "流程图", "时序图", "diagram", "chart"]):
            params["resource_type"] = "diagram"
        elif any(k in text for k in ["完整讲解", "图文视频", "讲透", "三合一", "全方位", "综合讲解"]):
            params["resource_type"] = "smart_tutoring"
        elif any(k in text for k in ["视频讲解", "生成视频", "视频脚本", "讲解视频", "video script", "slideshow"]):
            params["resource_type"] = "video_script"
        elif any(k in text for k in ["对比", "区别", "差异"]):
            params["resource_type"] = "document"
        elif any(k in text_lower for k in ["write a", "write code", "implement",
                                            "code example", "debug", "fix this"]):
            params["resource_type"] = "code_example"
        elif any(k in text_lower for k in ["mindmap", "mind map"]):
            params["resource_type"] = "mindmap"
        return {"intent": "resource", "params": params}

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
    # P1-FIX: 仅当 path_agent 输出了 teaching_stage (教学流中的路径规划) 才推荐下一步
    # 用户明确要"学习计划/路线图"时 (无 teaching_stage) 不自动触发后续 Agent
    if last_agent == "path_agent" and last_output.get("teaching_stage"):
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


# ═══════════════════════════════════════════════════════════
# supervisor_node 辅助函数 — A-01 职责拆分
# ═══════════════════════════════════════════════════════════

def _handle_agent_return(state: dict, agent_outputs: dict, current_agent: str,
                         last_msg: str, last_msg_lower: str,
                         _entry_time: float, _new_traces: list) -> dict:
    """处理 Agent 完成后的重入/链式路由 (原 supervisor_node 优先级-1)

    职责:
      1. Trace 记录已完成 Agent 的执行
      2. 教学流程链式路由: path_agent → resource_agent
      3. 画像优先流程: profile_agent 完成采集 → 回到原意图
      4. 教学模式智能推进: 阶段内自动前进，阶段边界暂停
      5. QA 协作链: question_agent ↔ evaluation_agent
      6. 评估薄弱维度检测 → 路径重规划
      7. BKT 掌握度变化检测 → 路径重规划
    """
    # ── Trace: 记录已完成 Agent 的执行 ──
    _trace_dispatch_ts = state.get("context", {}).get("_trace_dispatch_ts", _entry_time)
    _trace_intent = state.get("context", {}).get("_trace_intent", "")
    _stream_buf = state.get("stream_buffer", "") or ""
    _in_len = len(last_msg) if last_msg else 0
    _out_len = len(_stream_buf)
    _new_traces.append({
        "agent": current_agent,
        "start_ms": _trace_dispatch_ts,
        "end_ms": _entry_time,
        "input_tokens": max(0, _in_len // 4),
        "output_tokens": max(0, _out_len // 4),
        "intent": _trace_intent if _trace_intent else None,
        "input_preview": (last_msg or "")[:100],
        "output_preview": _stream_buf[:100],
        "error": None,
    })

    tc = state.get("teaching_context") or {}

    # ── 教学流程链式路由: path_join (path_agent+prefetch 并行完成后) → resource_agent ──
    if current_agent == "path_join":
        path_output = agent_outputs.get("path_agent", {})
        stage = path_output.get("teaching_stage", "")
        # P0-C 2026-07-11: 教学链 gate, 防止 checkpoint 残留 teaching_context 触发自动教学
        from app.agents._teaching_gate import should_init_teaching
        if not should_init_teaching(state, state.get("context", {})):
            logger.info("Supervisor: 教学 gate 拒绝 → path_join 正常结束, 不进入教学链")
            return {
                "current_agent": "supervisor",
                "next_agent": "END",
                "context": state.get("context", {}),
                "stream_buffer": path_output.get("stream_buffer", ""),
                "trace": _new_traces,
            }
        if stage in ("starting", "node_ready"):
            logger.info("Supervisor: 教学链式 %s → resource_agent (node=%s)", current_agent, path_output.get("current_node"))
            return {
                "current_agent": "supervisor",
                "next_agent": "resource_agent",
                "context": path_output.get("teach_context", state.get("context", {})),
                "teaching_context": state.get("teaching_context"),
                "stream_buffer": "",
                "trace": _new_traces,
            }
        if stage == "replanned":
            next_node = path_output.get("current_node", "")
            if next_node:
                logger.info("Supervisor: 路径重规划完成 → resource_agent (next=%s)", next_node)
                return {
                    "current_agent": "supervisor",
                    "next_agent": "resource_agent",
                    "context": {**state.get("context", {}), "topic": next_node, "teaching": True},
                    "teaching_context": state.get("teaching_context"),
                    "stream_buffer": "",
                    "trace": _new_traces,
                }
            logger.info("Supervisor: 路径重规划完成，无剩余节点 → END")
            return {
                "current_agent": "supervisor",
                "next_agent": "END",
                "context": state.get("context", {}),
                "stream_buffer": "",
                "trace": _new_traces,
            }
        # stage == "continue" or other: 仅当 path_agent 明确处于教学流中才继续
        # (空 stage + 无 teaching_stage key → 正常规划，不触发教学链)
        if stage or "teaching_stage" in path_output:
            tc_path = state.get("teaching_context") or {}
            if tc_path.get("mode") == "teaching" and tc_path.get("current_index", 0) < len(tc_path.get("active_path", [])):
                return {
                    "current_agent": "supervisor",
                    "next_agent": "resource_agent",
                    "context": {
                        **state.get("context", {}),
                        "topic": tc_path["active_path"][tc_path["current_index"]],
                        "teaching": True,
                    },
                    "teaching_context": tc_path,
                    "stream_buffer": "",
                    "trace": _new_traces,
                }
        if stage == "completed":
            logger.info("Supervisor: 教学流程已完成")
            return {
                "current_agent": "supervisor",
                "next_agent": "END",
                "context": state.get("context", {}),
                "stream_buffer": "",
                "trace": _new_traces,
            }

    # ── 画像优先流程: profile_agent 完成采集 → 回到原意图 ──
    if current_agent == "profile_agent":
        ctx = state.get("context", {})
        if ctx.get("profile_first"):
            filled_dims, _ = _get_profile_status(state.get("user_profile"))
            if len(filled_dims) >= 3:
                deferred = ctx.get("deferred_intent", "resource")
                logger.info("Supervisor: 画像采集完成(%d/6维) → 回到原意图 %s", len(filled_dims), deferred)
                route_map_agent = {
                    "resource": "collaborative_resource", "question": "collaborative_qa",
                    "path": "collaborative_path", "evaluation": "evaluation_agent",
                }
                return {
                    "current_agent": "supervisor",
                    "next_agent": route_map_agent.get(deferred, "resource_agent"),
                    "context": {
                        **ctx,
                        **ctx.get("deferred_context", {}),
                        "profile_first_done": True,
                    },
                    "teaching_context": {**tc, "profile_first_done": True},
                    "stream_buffer": "",
                    "trace": _new_traces,
                }
            else:
                logger.info("Supervisor: 画像不足(%d/6维)，保持 profile_first 待下一轮", len(filled_dims))
                return {
                    "current_agent": "supervisor",
                    "next_agent": "END",
                    "context": {
                        **ctx,
                        "profile_first": True,
                        "deferred_intent": ctx.get("deferred_intent", "resource"),
                    },
                    "stream_buffer": "",
                    "trace": _new_traces,
                }

    # ── 质量审查门: quality_reviewer 低分 → 难度重定向 ──
    if current_agent == "rc_join":
        qc = agent_outputs.get("quality_reviewer", {})
        qc_score = qc.get("score", 100)
        if qc_score < 60:
            qc_issues = qc.get("issues", [])
            difficulty_hint = qc.get("difficulty_target", "适中")
            logger.warning("Supervisor: 质量审查不通过 score=%d → 重新生成 (hint=%s)", qc_score, difficulty_hint)
            _retry_ctx = {**state.get("context", {}),
                          "_quality_retry": True,
                          "_quality_issues": qc_issues[:3],
                          "_difficulty_hint": difficulty_hint}
            return {
                "current_agent": "supervisor",
                "next_agent": "resource_agent",
                "context": _retry_ctx,
                "teaching_context": state.get("teaching_context"),
                "stream_buffer": "",
                "trace": _new_traces,
            }
        if qc_score < 75:
            _hint = qc.get("difficulty_target", "")
            logger.info("Supervisor: 质量审查偏低 score=%d hint=%s — 输出但标记", qc_score, _hint)
        # P3: 质量反馈传递 — 将审查建议注入 teaching_context，供后续 resource_agent 调用改进
        qc_issues = qc.get("issues", [])
        if qc_issues:
            tc["_quality_hints"] = {
                "issues": [i for i in qc_issues if not i.startswith("[")][:3],
                "difficulty_target": qc.get("difficulty_target", ""),
            }
            logger.info("Supervisor: 质量反馈已注入 teaching_context (%d issues)", len(qc_issues))

    # ── v5: 教学模式智能推进 ──
    if current_agent == "rc_join" and tc.get("mode") == "teaching":
        current_idx = tc.get("current_index", 0)
        total = len(tc.get("active_path", []))
        auto_count = tc.get("auto_advance_count", 0)

        if auto_count >= 3:
            logger.info("Supervisor: 教学 auto_advance 已达上限(%d) → END", auto_count)
            tc["auto_advance_count"] = 0
            return {
                "current_agent": "supervisor",
                "next_agent": "END",
                "context": state.get("context", {}),
                "teaching_context": tc,
                "stream_buffer": (
                    "\n\n---\n"
                    "> 已连续教学3个节点，暂停一下让你消化。\n"
                    "> 你可以：**[继续学]** / **[做练习题巩固]** / **[换个主题]**\n"
                ),
                "trace": _new_traces,
            }

        is_stage_boundary = (current_idx > 0 and (current_idx + 1) % 3 == 0)
        is_last_node = (current_idx + 1 >= total)

        if is_last_node:
            logger.info("Supervisor: 教学最后一个节点 → END")
            tc["auto_advance_count"] = 0
            return {
                "current_agent": "supervisor",
                "next_agent": "END",
                "context": state.get("context", {}),
                "teaching_context": tc,
                "stream_buffer": "",
                "trace": _new_traces,
            }
        elif is_stage_boundary:
            logger.info("Supervisor: 教学阶段边界 (index=%d/%d) → END with options", current_idx, total)
            tc["auto_advance_count"] = 0
            return {
                "current_agent": "supervisor",
                "next_agent": "END",
                "context": state.get("context", {}),
                "teaching_context": tc,
                "stream_buffer": "",
                "trace": _new_traces,
            }
        else:
            logger.info("Supervisor: 教学 auto-advance %d/%d → path_agent", current_idx + 1, total)
            tc["auto_advance_count"] = auto_count + 1
            return {
                "current_agent": "supervisor",
                "next_agent": "path_agent",
                "context": {**state.get("context", {}), "teaching_continue": True},
                "teaching_context": tc,
                "stream_buffer": "",
                "trace": _new_traces,
            }

    # ── v5.2: profile_agent 完成后 → 延迟意图链式路由 ──
    if current_agent == "profile_agent":
        ctx = state.get("context") or {}
        deferred_intent = ctx.get("deferred_intent")
        if deferred_intent:
            filled_dims, _ = _get_profile_status(state.get("user_profile"))
            if len(filled_dims) >= 3:
                deferred_params = ctx.get("deferred_params", {})
                _intern_route = {
                    "profile": "profile_agent",
                    "resource": "resource_agent",
                    "question": "question_agent",
                    "path": "path_agent",
                    "evaluation": "evaluation_agent",
                }
                next_deferred = _intern_route.get(deferred_intent, "chat_agent")
                logger.info("Supervisor: 画像采集完成(%d/6维) → 路由到延迟意图 %s → %s",
                            len(filled_dims), deferred_intent, next_deferred)
                return {
                    "current_agent": "supervisor",
                    "next_agent": next_deferred,
                    "context": {**state.get("context", {}), **(deferred_params or {})},
                    "stream_buffer": "",
                    "trace": _new_traces,
                }
            else:
                logger.info("Supervisor: 画像采集中(%d/6维，需≥3) → 等待下一轮", len(filled_dims))

    # ── QA 协作链 (A→B→A) ──
    if current_agent == "qa_join":
        ctx = state.get("context", {})
        merged_ao = state.get("agent_outputs", {})

        # 独立 evaluation 调用 → 薄弱维度检测 (非 QA 链场景)
        if not ctx.get("_qa_stage"):
            eval_out = merged_ao.get("evaluation_agent", {})
            weak_dims = eval_out.get("dimension_scores", {})
            if any(v < 40 for v in weak_dims.values() if isinstance(v, (int, float))):
                logger.info("Supervisor: standalone eval weak dim detected → replan path_agent")
                return {
                    "current_agent": "supervisor",
                    "next_agent": "path_agent",
                    "context": {**ctx, "replan_path": True, "_replan_reason": "eval_weak_dim"},
                    "stream_buffer": "",
                    "trace": _new_traces,
                }

        qa_stage = ctx.get("_qa_stage", "")

        if qa_stage == "first_review":
            if merged_ao.get("evaluation_agent"):
                logger.info("Supervisor: QA 协作链 审核完成(evaluation_agent) → question_agent 修正")
                return {
                    "current_agent": "supervisor",
                    "next_agent": "question_agent",
                    "context": {**ctx, "_qa_stage": "revision"},
                    "stream_buffer": "",
                    "trace": _new_traces,
                }
            else:
                logger.warning("Supervisor: QA reviewing 但 evaluation_agent 输出缺失，重置")
                ctx.pop("_qa_stage", None)

        elif qa_stage == "revision":
            if merged_ao.get("question_agent"):
                _eval_out = merged_ao.get("evaluation_agent", {})
                _weak_dims = _eval_out.get("dimension_scores", {})
                if any(v < 40 for v in _weak_dims.values() if isinstance(v, (int, float))):
                    logger.info("Supervisor: QA 协作链 修正完成 + eval弱维度检测 → 触发路径重规划")
                    return {
                        "current_agent": "supervisor",
                        "next_agent": "path_agent",
                        "context": {**ctx, "_qa_stage": "", "replan_path": True, "_replan_reason": "qa_eval_weak_dim"},
                        "stream_buffer": "",
                        "trace": _new_traces,
                    }
                logger.info("Supervisor: QA 协作链 修正完成(question_agent) → END")
                return {
                    "current_agent": "supervisor",
                    "next_agent": "END",
                    "context": {**ctx, "_qa_stage": ""},
                    "stream_buffer": "",
                    "trace": _new_traces,
                }

    # ── BKT 闭环: 掌握度变化 → 路径重规划 (join节点后检查) ──
    if current_agent in ("rc_join", "qa_join"):
        _ctx_bkt = state.get("context", {})
        if _ctx_bkt.get("_bkt_relevant"):
            try:
                from app.services.bkt_service import get_tracker
                tracker = get_tracker(state.get("user_id", 0))
                prev_mastered = set(_ctx_bkt.get("_last_bkt_mastered", []))
                current_mastered = set(tracker.get_mastered())
                newly_mastered = current_mastered - prev_mastered
                if newly_mastered and prev_mastered:
                    logger.info("Supervisor: BKT mastered set changed +%s → replan path_agent", list(newly_mastered))
                    return {
                        "current_agent": "supervisor",
                        "next_agent": "path_agent",
                        "context": {**_ctx_bkt, "replan_path": True,
                                     "_last_bkt_mastered": list(current_mastered),
                                     "_replan_reason": "bkt_new_mastery", "_bkt_relevant": False},
                        "stream_buffer": "",
                        "trace": _new_traces,
                    }
            except Exception as _bkt_err:
                logger.warning("Supervisor: BKT闭环检测失败 (non-fatal): %s", _bkt_err)
        else:
            logger.debug("Supervisor: 跳过BKT检测 (agent=%s, _bkt_relevant未设置)", current_agent)

    # ── 默认: 结束当前轮次 ──
    logger.info("Supervisor: Agent '%s' 已完成，结束当前轮次", current_agent)
    return {
        "current_agent": "supervisor",
        "next_agent": "END",
        "context": state.get("context", {}),
        "stream_buffer": "",
        "trace": _new_traces,
    }


def _classify_intent(last_msg: str, last_msg_lower: str, all_messages: list,
                     profile: dict, spark) -> tuple:
    """意图分类: 关键词优先 + LLM 兜底

    返回 (intent: str, result: dict)
    """
    filled_dims, empty_dims = _get_profile_status(profile)
    system_prompt = SUPERVISOR_PROMPT
    if empty_dims:
        system_prompt += SUPERVISOR_PROFILE_CONTEXT.format(
            filled_dims=", ".join(filled_dims) if filled_dims else "(无)",
            empty_dims=", ".join(empty_dims),
        )

    kw_result = _keyword_fallback(last_msg)
    kw_intent = kw_result["intent"]

    if kw_intent != "chat":
        intent = kw_intent
        result = kw_result
        logger.info("Supervisor: keyword routing intent=%s (skipping LLM)", intent)
    else:
        classify_context = []
        for msg in all_messages[-6:]:
            content = str(getattr(msg, 'content', msg))
            msg_type = type(msg).__name__
            if 'Human' in msg_type:
                classify_context.append({"role": "user", "content": content[:300]})
            elif 'AI' in msg_type:
                classify_context.append({"role": "assistant", "content": content[:200]})
        if not classify_context or classify_context[-1].get("role") != "user":
            classify_context.append({"role": "user", "content": last_msg})

        classify_messages = [{"role": "system", "content": system_prompt}] + classify_context

        raw = ""
        try:
            raw = spark.chat_sync(classify_messages, temperature=0.3)
            result = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        except Exception:
            match = re.search(r'"intent"\s*:\s*"(\w+)"', raw)
            if match:
                result = {"intent": match.group(1), "params": {}}
            else:
                result = {"intent": "chat", "params": {}}

        intent = result.get("intent", "chat")
        logger.info("Supervisor: LLM fallback intent=%s", intent)

        # Extra guard: LLM 误判 question → resource correction
        if intent == "question":
            has_strong_q = (
                re.search(r'(?:give|generate|create|make)\s+me\s+(?:\d+\s+)?(?:\w+\s+){0,5}(?:problems?|questions?|exercises?|challenges?|quiz)', last_msg_lower)
                or any(k in last_msg for k in ["出题", "做题", "刷题", "题目", "几道", "测试"])
            )
            if not has_strong_q:
                intent = "resource"
                logger.info("Supervisor: LLM question→resource correction")

    return intent, result


def _route_with_guards(intent: str, result: dict, state: dict, profile: dict,
                       last_msg: str, last_msg_lower: str,
                       _new_traces: list, _entry_time: float) -> dict:
    """路由映射 + 画像优先守卫 + 教学初始化 + trace 记录

    返回最终路由 dict (供 supervisor_node return)。
    """
    tc = state.get("teaching_context") or {}
    context_result = result.get("params", {})

    route_map = {
        "profile": "profile_agent",
        "resource": "collaborative_resource",
        "question": "question_agent",
        "path": "collaborative_path",
        "evaluation": "evaluation_agent",
        "chat": "chat_agent",
        "teaching_continue": "path_agent",
    }
    next_agent = route_map.get(intent, "chat_agent")

    # P2-01: resource explain mode → resource_agent (no collaboration)
    if intent == "resource":
        resource_mode = context_result.get("mode", "explain")
        if resource_mode == "explain":
            next_agent = "resource_agent"
            logger.info("Supervisor: resource explain mode → resource_agent (no collaboration)")

    # QA 协作链初始化
    if intent == "question":
        context_result = {**context_result, "_qa_stage": "first_review"}
        logger.info("Supervisor: QA 协作链 初始化 _qa_stage=first_review")

    # evaluation 路由: 标记 BKT 相关
    if intent == "evaluation":
        context_result = {**context_result, "_bkt_relevant": True}

    # 教学流程初始化: 广泛学习请求 → path_agent (with init_teaching)
    # P0 fix: intent=="path" (制定计划/规划) 不自动启动教学，仅生成计划展示
    if intent in ("resource", "path") and (not tc or not tc.get("mode")):
        if _is_broad_learning_request(last_msg):
            if intent == "resource":
                next_agent = "path_agent"
                # 仅 resource intent (想学/教我) 才自动启动教学
                context_result = dict(context_result)
                context_result["init_teaching"] = True
            # intent == "path" 时仅生成学习计划，不自动开始教学
            logger.info("Supervisor: 广泛学习请求 → 启动教学流程 (via %s)", next_agent)

    # 教学引用解析: 在 teaching 模式下将"第X天"映射到 active_path 实际知识点
    if intent == "resource" and tc and tc.get("mode") == "teaching":
        resolved = resolve_teaching_reference(last_msg, tc)
        if resolved:
            context_result = dict(context_result)
            context_result["topic"] = resolved["topic"]
            context_result["node_index"] = resolved["index"]
            logger.info("Supervisor: 教学引用 → 覆盖 topic='%s'", resolved["topic"])

    # ── 新用户画像优先守卫 ──
    if not tc or not tc.get("mode"):
        filled_dims, _ = _get_profile_status(profile)
        ctx = state.get("context", {})
        profile_first_done = ctx.get("profile_first_done", False) or tc.get("profile_first_done", False)
        ask_count = ctx.get("profile_ask_count", 0)
        MAX_ASK_PER_SESSION = 2
        _emergency_keywords = ["报错", "为什么错", "bug", "error", "fix", "debug", "错在哪",
                               "评估一下", "看一下我的水平", "紧急"]
        _is_emergency = any(kw in last_msg_lower for kw in _emergency_keywords) or \
                        next_agent in ("evaluation_agent",)
        _casual_greetings = ["你好", "hi", "hello", "嗨", "在吗", "你是谁", "你能做什么",
                             "介绍一下", "你是什么", "有什么功能", "你会什么"]
        _is_casual = any(kw in last_msg_lower for kw in _casual_greetings) or \
                     next_agent in ("profile_agent",)
        if (len(filled_dims) < 2
                and not profile_first_done
                and ask_count < MAX_ASK_PER_SESSION
                and not _is_emergency
                and not _is_casual):
            logger.info("Supervisor: 画像极稀疏(%d/6维, ask_count=%d) → profile_agent 优先 (defer %s)",
                        len(filled_dims), ask_count, next_agent)
            _agent_node_to_intent = {
                "resource_agent": "resource", "question_agent": "question",
                "path_agent": "path", "evaluation_agent": "evaluation",
                "profile_agent": "profile", "chat_agent": "chat",
                "collaborative_resource": "resource", "collaborative_qa": "question",
                "collaborative_path": "path",
            }
            _deferred_intent = _agent_node_to_intent.get(next_agent, next_agent.replace("_agent", ""))
            _next_ask_count = ask_count + 1
            _ctx_update: dict = {
                "profile_first": True,
                "deferred_intent": _deferred_intent,
                "deferred_params": context_result,
                "deferred_message": last_msg,
                "profile_ask_count": _next_ask_count,
            }
            if _next_ask_count >= MAX_ASK_PER_SESSION:
                _ctx_update["profile_first_done"] = True
                logger.info("Supervisor: 画像采集达上限(ask_count=%d) → profile_first_done 持久化", _next_ask_count)
            _tc_update = {}
            if _ctx_update.get("profile_first_done"):
                _tc_update["profile_first_done"] = True
            return {
                "current_agent": "supervisor",
                "next_agent": "profile_agent",
                "context": {**state.get("context", {}), **_ctx_update},
                "teaching_context": {**tc, **_tc_update} if _tc_update else tc,
                "stream_buffer": "",
                "trace": _new_traces,
            }

    logger.info("Supervisor: intent=%s → route=%s", intent, next_agent)

    # ── Trace: 记录 Supervisor 意图分类 ──
    _supervisor_end = time.time() * 1000
    _in_len_final = len(last_msg) if last_msg else 0
    _new_traces.append({
        "agent": "supervisor",
        "start_ms": _entry_time,
        "end_ms": _supervisor_end,
        "input_tokens": max(0, _in_len_final // 4),
        "output_tokens": 30,
        "intent": intent,
        "input_preview": (last_msg or "")[:100],
        "output_preview": f"intent={intent}, route={next_agent}",
        "error": None,
    })
    context_result["_trace_dispatch_ts"] = time.time() * 1000
    context_result["_trace_intent"] = intent

    return {
        "current_agent": "supervisor",
        "next_agent": next_agent,
        "context": {**state.get("context", {}), **context_result},
        "trace": _new_traces,
    }


#state读取当前状态--调用星火api判断意图
def supervisor_node(state: AgentState, spark: SparkClient) -> dict:
    """Supervisor 节点: 编排器 — 协调辅助函数完成意图分类与路由 (A-01 重构)"""
    state = dict(state)
    last_msg = last_msg_content(state.get("messages", []))
    last_msg_lower = last_msg.lower()
    profile = state.get("user_profile") or {}

    # ── Trace: 入口计时 ──
    _entry_time = time.time() * 1000
    _new_traces: list[dict] = []

    # ── Profile dirty-check: Redis 标记 → DB 重载 ──
    user_id = state.get("user_id", 0)
    if user_id:
        try:
            from app.core.security import _get_redis
            r = _get_redis()
            if r is None:
                logger.debug("Supervisor: Redis 不可用，跳过画像脏标记检查")
            else:
                flag_key = f"profile_dirty:{user_id}"
                if r.get(flag_key):
                    r.delete(flag_key)
                    from app.core.database import get_session
                    from app.models.profile import LearningProfile
                    try:
                        with get_session() as db:
                            row = db.query(LearningProfile).filter(LearningProfile.user_id == user_id).first()
                            if row:
                                profile = {
                                    "knowledge_base": row.knowledge_base,
                                    "cognitive_style": row.cognitive_style,
                                    "learning_goal": row.learning_goal,
                                    "weekly_hours": row.weekly_hours,
                                    "preferred_resource_type": row.preferred_resource_type,
                                    "error_patterns": row.error_patterns,
                                    "dimension_scores": row.dimension_scores,
                                }
                                state["user_profile"] = profile
                                logger.info("Supervisor: 静默画像变更 → 已重新加载 profile (user_id=%d)", user_id)
                    except Exception:
                        pass
        except Exception:
            pass

    all_messages = state.get("messages", [])
    agent_outputs = state.get("agent_outputs", {})
    current_agent = state.get("current_agent", "supervisor")

    # ── 守卫: 新意图检测 ──
    _already_handled = state.get("context", {}).get("_new_intent_handled")
    if (not _already_handled
            and current_agent != "supervisor"
            and _has_explicit_new_intent(last_msg, last_msg_lower)):
        logger.info("Supervisor: 检测到新的明确意图 '%s'，重置教学上下文 → 走正常分类", last_msg[:40])
        state["current_agent"] = "supervisor"
        state["teaching_context"] = None
        state["context"] = {**state.get("context", {}), "_new_intent_handled": True}
        current_agent = "supervisor"

    # ── 优先级-1: Agent 重入路由 ──
    if current_agent != "supervisor":
        return _handle_agent_return(state, agent_outputs, current_agent,
                                    last_msg, last_msg_lower, _entry_time, _new_traces)

    tc = state.get("teaching_context") or {}

    # ── 优先级0: 教学流程继续 ──
    if tc.get("mode") == "teaching" and is_teaching_continue(last_msg, tc):
        _tc_ctx = {**state.get("context", {}), "teaching_continue": True}
        # 解析教学引用: 用户指定了具体第X天 → 跳转到目标索引
        _ref = _resolve_teaching_reference(last_msg, tc)
        if _ref and _ref.get("index", 0) != tc.get("current_index", 0) + 1:
            _tc_ctx["teach_target_index"] = _ref["index"]
            _tc_ctx["topic"] = _ref["topic"]
            logger.info("Supervisor: 教学跳转 → index=%d node='%s'", _ref["index"], _ref["topic"])
        else:
            logger.info("Supervisor: 教学流程继续 → path_agent (advance index=%d, total=%d)",
                         tc.get("current_index", 0), len(tc.get("active_path", [])))
        return {
            "current_agent": "supervisor",
            "next_agent": "path_agent",
            "context": _tc_ctx,
            "teaching_context": tc,
            "stream_buffer": "",
            "trace": _new_traces,
        }

    # ── 优先级1: 答案提交检测 ──
    if is_answer_submission(last_msg):
        logger.info("Supervisor: 检测到答案提交格式 → question_agent")
        return {
            "current_agent": "supervisor",
            "next_agent": "question_agent",
            "context": {**state.get("context", {}), "_bkt_relevant": True},
            "stream_buffer": "",
            "trace": _new_traces,
        }

    # ── 优先级1: 主动调度 ──
    passive_confirm = re.match(r'^(好|好的|可以|行|来|开始|没问题|嗯|OK|ok|yes|是|对|继续)$', last_msg.strip())
    if passive_confirm and len(all_messages) >= 2:
        for msg in reversed(all_messages[:-1]):
            prev_agent = getattr(msg, 'additional_kwargs', {}).get('agent', '')
            if prev_agent and prev_agent != 'chat':
                prev_output = agent_outputs.get(prev_agent, {})
                proactive = _proactive_suggest(prev_agent, prev_output)
                if proactive:
                    logger.info("Supervisor: 主动调度 %s → %s (原因: %s)",
                                prev_agent, proactive["intent"], proactive["reason"])
                    route_map_pa = {
                        "profile": "profile_agent",
                        "resource": "resource_agent",
                        "question": "question_agent",
                        "path": "path_agent",
                        "evaluation": "evaluation_agent",
                    }
                    next_agent_pa = route_map_pa.get(proactive["intent"], "END")
                    return {
                        "current_agent": "supervisor",
                        "next_agent": next_agent_pa,
                        "context": {**state.get("context", {}), **proactive.get("params", {})},
                        "stream_buffer": "",
                        "trace": _new_traces,
                    }
                break

    # ── 优先级2: 意图分类 → 路由 ──
    intent, result = _classify_intent(last_msg, last_msg_lower, all_messages, profile, spark)
    return _route_with_guards(intent, result, state, profile, last_msg, last_msg_lower,
                               _new_traces, _entry_time)

# 构建 LangGraph 图 (v3)


def supervisor_router(state):
    na = state.get("next_agent", "END") if isinstance(state, dict) else getattr(state, "next_agent", "END")
    fork_map = {
        "collaborative_qa": ("question_agent", "evaluation_agent"),
        "collaborative_resource": ("resource_agent", "quality_reviewer"),
        "collaborative_path": ("path_agent", "prefetch_agent"),
    }
    if na in fork_map:
        a, b = fork_map[na]
        s = dict(state) if isinstance(state, dict) else state.model_dump()
        return [Send(a, s), Send(b, s)]
    return na

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
    workflow.add_node("qa_join", qa_join_node)
    workflow.add_node("rc_join", rc_join_node)
    workflow.add_node("path_join", path_join_node)
    workflow.add_node("quality_reviewer", lambda s: _quality_review_node(s))
    workflow.add_node("prefetch_agent", _prefetch_resource_meta)

    workflow.set_entry_point("supervisor")

    # ── Supervisor 条件路由 ──
    workflow.add_conditional_edges(
        "supervisor",
        supervisor_router,
        {
            "chat_agent": "chat_agent",
            "profile_agent": "profile_agent",
            "resource_agent": "resource_agent",
            "question_agent": "question_agent",
            "path_agent": "path_agent",
            "evaluation_agent": "evaluation_agent",
            "quality_reviewer": "quality_reviewer",
            "prefetch_agent": "prefetch_agent",
            "qa_join": "qa_join",
            "rc_join": "rc_join",
            "path_join": "path_join",
            "END": END,
        },
    )

    # ── Worker edges: worker → supervisor (保留 bridge 模式, 非终端) ──
    workflow.add_edge("profile_agent", "supervisor")
    workflow.add_edge("question_agent", "qa_join")
    workflow.add_edge("evaluation_agent", "qa_join")
    workflow.add_edge("qa_join", "supervisor")
    workflow.add_edge("resource_agent", "rc_join")
    workflow.add_edge("quality_reviewer", "rc_join")
    workflow.add_edge("rc_join", "supervisor")
    workflow.add_edge("path_agent", "path_join")
    workflow.add_edge("prefetch_agent", "path_join")
    workflow.add_edge("path_join", "supervisor")
    # Chat Agent → END (终端: 聊天回复后直接结束)
    workflow.add_edge("chat_agent", END)

    # ── 编译 (SQLite checkpoint 持久化) ──
    db_path = settings.checkpoint_db_path
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    checkpointer = SqliteSaver(db_path=db_path)
    return workflow.compile(checkpointer=checkpointer)
