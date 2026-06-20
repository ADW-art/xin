"""
Question Agent — 自适应出题 + 答案收集 + 智能打分

双模式工作流：
1. 出题模式（默认）：根据画像+BKT生成题目，末尾引导用户提交答案
2. 评阅模式：用户提交答案后自动触发，逐题批改+BKT更新+自适应调难度

自适应逻辑：
- 连续答对2次 → 升难度
- 答错1次 → 降难度 + 标记薄弱点
- 正确率≥80% → 推荐进阶/相关主题
- 正确率<50% → 推荐先复习基础
"""

import json
import logging
import re

from app.agents.state import AgentState
from app.services.spark_client import SparkClient
from app.services.bkt_service import get_tracker
from app.services.rag_service import search_exercises

logger = logging.getLogger(__name__)

# ============================================================
# 题目缓存：Agent 不自行调用 LLM，LLM 调用由 _bridge_stream 负责
# 生成后的完整题目文本由 chat.py 写入此缓存，供后续评阅模式使用
# ============================================================
# v3: 使用 functools.lru_cache 替代模块级 dict (自动淘汰 + 防内存泄漏)
import functools
import time as _time

_last_questions_cache: dict[int, tuple[str, float]] = {}  # {user_id: (text, timestamp)}
_CACHE_TTL_SECONDS = 3600  # 1小时过期
_MAX_CACHE_SIZE = 128

def _evict_expired() -> None:
    """清除过期缓存条目"""
    now = _time.time()
    expired = [uid for uid, (_, ts) in _last_questions_cache.items() if now - ts > _CACHE_TTL_SECONDS]
    for uid in expired:
        del _last_questions_cache[uid]

def cache_questions_text(user_id: int, text: str) -> None:
    """chat.py 在流式完成后调用，缓存完整题目文本供下次评阅使用"""
    if user_id and text:
        _evict_expired()  # 写入前清理过期条目
        if len(_last_questions_cache) >= _MAX_CACHE_SIZE:
            # 淘汰最旧的条目
            oldest = min(_last_questions_cache.items(), key=lambda x: x[1][1])
            del _last_questions_cache[oldest[0]]
        _last_questions_cache[user_id] = (text, _time.time())
        logger.info("QuestionAgent: 已缓存题目文本 user_id=%d len=%d (cache_size=%d)",
                     user_id, len(text), len(_last_questions_cache))

def _get_cached_questions(user_id: int) -> str:
    """获取缓存的题目文本；TTL过期或缓存未命中返回空字符串"""
    entry = _last_questions_cache.get(user_id)
    if entry:
        text, ts = entry
        if _time.time() - ts < _CACHE_TTL_SECONDS:
            return text
        del _last_questions_cache[user_id]
    return ""

# ============================================================
# 答案格式检测：判断用户消息是否为题目答案
# ============================================================
ANSWER_PATTERNS = [
    r'^[1-9][\s]*[A-Da-d]',           # "1A" "1 A" "1a"
    r'^[1-9][\s]*[A-Da-d][\s]*[1-9]', # "1A2B" "1 a 2 b"
    r'^[1-9][\s]*(?:正确|错误|对|错)', # "1对" "1 错误"
    r'^(?:答案是?|答案)[:\s]',         # "答案是: ..." "答案：..."
    r'^(?:选|填|我的答案)',              # "选A" "填xxx" — but NOT "写" (too common: "写代码")
    # Fixed: only match single A-D letter at start of line or after numbering (not the English article "a")
    r'^[A-Da-d](?:$|[\s,，/]+)',       # Single letter answer at start of text
    r'(?<=\d)[A-Da-d](?:$|[\s,，/]+)', # Letter answer after a number e.g. "1A"
    r'def\s+\w+\s*\(.*\):',            # Python代码答案 (only at start of line or after newline)
    r'^\[[\w\s,]+\]$',                 # 列表/集合答案 (must be the entire message)
    r'^(?:True|False|None|\d+)$',       # 布尔/数字简答 (entire message)
]


def is_answer_submission(text: str) -> bool:
    """检测用户消息是否为题目答案提交"""
    text = text.strip()
    if len(text) < 1 or len(text) > 500:
        return False
    # 太长的自然语言不像答案
    if len(text) > 100 and not re.search(r'[A-Da-d]', text):
        return False
    for pattern in ANSWER_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def extract_answer_map(text: str, num_questions: int = 3) -> dict:
    """从用户输入中提取 题号→答案 的映射

    支持格式: "1A 2B 3xxx" / "A B C" / "1:A 2:B"
    返回: {1: "A", 2: "B", 3: "xxx"}
    """
    text = text.strip()
    result = {}

    # 格式1: 显式题号 "1A 2B 3xxx" 或 "1:A 2:B"
    explicit = re.findall(r'(\d+)\s*[:：]?\s*([A-Za-z0-9_\[\]\'\"\s]{1,100})', text)
    if explicit:
        for qnum, ans in explicit:
            try:
                qn = int(qnum)
                if 1 <= qn <= num_questions:
                    result[qn] = ans.strip()[:50]
            except ValueError:
                pass

    # 格式2: 无题号顺序 "A B C" 或 "abc"
    if not result and len(text.split()) <= num_questions * 2:
        parts = re.split(r'[\s,，/、]+', text)
        clean_parts = [p.strip().upper() for p in parts if p.strip() and len(p.strip()) <= 20]
        if all(re.match(r'^[A-D]$', p) or re.match(r'^[\w\[\](){}\"\'\/+=*!@#$%^&~`-]+$', p) for p in clean_parts):
            for i, part in enumerate(clean_parts[:num_questions]):
                result[i + 1] = part

    return result


# ============================================================
# Prompt 模板
# ============================================================

QUESTION_PROMPT = """你是一个自适应出题专家，对标 LeetCode + 洛谷出题质量。根据学生学习画像和当前阶段，生成语言特定的高质量题目。

## 学生画像
- 知识基础：{knowledge_base}
- 认知风格：{cognitive_style}
- 当前难度：{difficulty}

## 题目主题
{topic}

## 出题铁律（违反即为不合格）
1. 禁止出死记硬背题（"以下哪个是XXX的定义"）— 所有题目必须考察理解
2. 禁止编造不存在的函数/类/语法（is_prime()、delete_all()、magic_sort() 等不存在）
3. 禁止选择题的干扰项用臆造概念 — 干扰项必须是真实常见错误
4. 禁止代码题没有输入输出示例 — 每道代码题必须给定至少一组输入→输出
5. 禁止"以下说法正确的是"这种万能模板 — 每个选项必须有具体的技术内容

## 题型与分布（共{count}道，必须全部出）

### 第1道 — 概念理解题（选择题）— 难度：{difficulty}
- 4个选项 A/B/C/D，每个有明确技术内容，干扰项来自真实易错点
- 考察对核心概念的理解深度，不考记忆
- 正确示范考察内容：「给一个装饰器计时的例子，问输出顺序是什么」— 考执行时序
- 错误示范：「装饰器的语法是@作用在___」— 考记忆，不出

### 第2道 — 代码阅读题 — 难度：{difficulty}
- 给出5-15行完整代码，问输出是什么
- 考察代码追踪能力、变量作用域、执行顺序
- 代码必须能实际运行并产生确定输出
- 附：输入输出示例

### 第3道 — 代码编写题 — 难度：{difficulty}
- 给出函数签名 + 输入输出示例 + 约束条件（时间/空间限制、允许/禁止使用的语法）
- 考察动手能力、边界条件处理
- 必须指明：输入范围（如 1 <= n <= 1000）、不允许的做法（如不能使用全局变量）

## 每道题必须包含的字段
```
### 第 N 题 — [选择题/代码阅读/代码编写] — 难度：[简单/中等/较难] — 预计 [2-10] 分钟

**考察知识点**：[知识点1, 知识点2, 知识点3]

[题目正文]
- 选择题：必须列出 A/B/C/D 四个选项
- 代码题：给出函数签名 + 输入输出示例 + 约束条件

> **答案**：[正确答案或完整可运行代码]
> **解析**：
> - 逐选项/逐行解释为什么对
> - 逐选项/逐行解释为什么错
> - 标注易错点（学生最容易在这里掉坑）
```

## 编程语言约束（系统内部指令，不要输出给用户）
- 必须使用对话历史中用户指定的编程语言（Python/C++/Java/JavaScript）
- 如果用户未指定语言，默认使用 Python
- 只能使用该语言标准库和官方文档中真实存在的函数/类/语法
- 如果对话历史中有排除约束（"不要算法""不要递归""只用基础语法"），必须严格遵守

## 难度自适应
- 当前难度为{difficulty}（基于BKT知识追踪算法推算）
- 简单：单一概念，直接应用，不需要组合多个知识点
- 中等：需要组合2-3个概念，有1-2个边界条件需处理
- 较难：需要分析最优方案，有多处易错陷阱

格式：
### 第 N 题（题型）
题目内容...
A. 选项A  B. 选项B  C. 选项C  D. 选项D （如果是选择题）

> **答案**：X（选择题）或完整代码（代码题）
> **解析**：详细解释对错 + 易错点标注

---

**【主动引导 — 重要！】**

如果用户的请求不够具体（比如只说"出题"但没有指定主题）：
> 我注意到你还没有指定具体的知识点。你想练习哪个方向？比如：
> - C++基础（指针、引用、STL容器）
> - 数据结构（链表、树、图、排序算法）
> - 面向对象编程（类、继承、多态、虚函数）

否则，回复结束后加上：
> 请把你的答案发给我，格式如 "1A 2代码内容 3完整代码"，我会逐题批改并分析掌握情况"""


GRADE_PROMPT = """你是一个智能阅卷老师。请批改学生的答题结果，并诊断知识薄弱点。

## 原始题目（含标准答案和解析）
{questions_text}

## 学生提交的答案
{user_answers}

## 批改要求（每题必须完成以下4步）

### 第 N 题：正确 / 错误

1. 判断正误（写"正确"或"错误"——BKT 算法依赖这两个精确词解析，必须原样输出）
2. 如果正确：表扬要具体到考察的知识点（如"变量作用域理解正确"），不能只说"答对了"
3. 如果错误：必须做到以下3点：
   a. 给出正确答案
   b. 指出错误的具体原因（是概念混淆？边界遗漏？语法不熟？而非笼统说"不对"）
   c. 指出这个错误暴露的知识薄弱点（如"这说明你对闭包中变量捕获时机的理解还不够"）
4. 每题末尾标注该题考察的核心知识点

### 本轮成绩
- 正确率：X/Y（XX%）
- 知识薄弱点汇总：列出所有答错题目暴露的共同薄弱环节（如有）
- 评价：（基于正确率和薄弱点模式，给一条有针对性的鼓励，禁止说"别灰心""加油"等空洞安慰）

---

**重要：根据正确率，给出下一步推荐（用 > 引用格式，只加1条最合适的）：**
- 正确率 >= 80% 且有错题：> 这轮表现不错。错的那道题考察的是 [知识点名]，要我给你系统讲一遍吗？
- 正确率 = 100%：> 全对！要挑战更高难度的题目吗？或者换个新主题继续？
- 正确率 50%-80%：> 你错的主要是 [知识点] 类型的问题。要我针对这个薄弱点出几道专项练习吗？
- 正确率 < 50%：> 这些知识点掌握得还不太熟。要从头讲一遍 [核心知识点] 吗？我会用代码示例逐点说明。

禁止的推荐语："很棒""别灰心""加油""多练习"——必须给出具体知识点的下一步行动"""


def question_agent_node(state: AgentState, spark: SparkClient) -> dict:
    """Question Agent 主逻辑：出题 or 评阅 双模式"""
    state = dict(state)  # TypedDict → dict
    profile = state.get("user_profile") or {}
    context = state.get("context", {})
    last_msg = state["messages"][-1].content if state["messages"] else ""
    user_id = state.get("user_id", 0)

    tracker = get_tracker(user_id)

    # ── 模式检测：用户是否在提交答案？ ──
    # 从 agent_outputs 中取出上次出的题目（用于评阅模式）
    last_output = state.get("agent_outputs", {}).get("question_agent", {})
    last_questions_text = last_output.get("last_questions_text", "")
    last_topic = last_output.get("topic", "")
    last_count = last_output.get("question_count", 3)

    # 优先取 agent_outputs 中的题目文本，降级到内存缓存（Agent 不自行调 LLM 后由 chat.py 写入）
    effective_questions_text = last_questions_text or _get_cached_questions(user_id)

    if is_answer_submission(last_msg) and effective_questions_text:
        # ════════════════════════════════════
        # 评阅模式：批改答案 + BKT更新 + 自适应
        # ════════════════════════════════════
        logger.info("QuestionAgent: 检测到答案提交，进入评阅模式")

        answer_map = extract_answer_map(last_msg, last_count)

        messages = [{"role": "system", "content": GRADE_PROMPT.format(
            questions_text=effective_questions_text,
            user_answers=json.dumps(answer_map, ensure_ascii=False, indent=2),
        )}]

        from app.utils.llm_helper import truncate_messages
        messages = truncate_messages(messages, max_tokens=6000)

        # BKT 更新推迟到 LLM 批改完成后执行（chat.py _persist_agent_output 触发）
        # 届时将解析 GRADE_PROMPT 的 LLM 回复，提取每题正误后逐题更新 BKT
        # 这样 BKT 接收的是真实的批改结果，而非随机猜测

        return {
            "current_agent": "question_agent",
            "stream_buffer": "",
            "agent_outputs": {
                **state.get("agent_outputs", {}),
                "question_agent": {
                    "mode": "grade",
                    "topic": last_topic,
                    "answers": answer_map,
                    "bkt_p_known": tracker.get_or_create(last_topic).p_known,
                    "stream_pending": {
                        "messages": messages,
                        "temperature": 0.4,
                        "max_tokens": 4096,
                    },
                },
            },
        }

    else:
        # ════════════════════════════════════
        # 出题模式：生成新题目 + 引导提交答案
        # ════════════════════════════════════
        topic = context.get("topic", last_msg)
        kb = profile.get("knowledge_base", {"未评估": "未知"})

        # 读取话题上下文（用户语言偏好 + 排除约束）
        topic_ctx = context.get("topic_context", {})
        user_lang = topic_ctx.get("user_language", "")
        user_constraints = topic_ctx.get("user_constraints", [])

        # 如果用户指定了语言，在主题中标注
        if user_lang:
            topic = f"{topic}（使用{user_lang}语言）"
        if user_constraints:
            exclude_text = "、".join(user_constraints)
            topic = f"{topic}（排除：{exclude_text}）"

        # BKT 自适应难度
        difficulty = tracker.get_difficulty(topic)
        logger.info("QuestionAgent: 出题模式 难度=%s 主题=%s p_known=%.3f",
                     difficulty, topic, tracker.get_or_create(topic).p_known)

        # 题库 RAG 检索
        references = ""
        try:
            ex_results = search_exercises(topic, difficulty=difficulty, n=3)
            if ex_results:
                ref_parts = [r["content"][:300] for r in ex_results]
                references = "\n\n---\n\n".join(ref_parts)
                logger.info("QuestionAgent: 题库检索到 %d 道参考题", len(ex_results))
        except Exception as e:
            logger.warning("QuestionAgent: 题库检索失败: %s", e)

        ref_block = f"\n## 参考题目（请改编，不要照抄）\n{references}\n" if references else ""

        question_count = 3  # 默认出3道

        question_system = QUESTION_PROMPT.format(
            knowledge_base=str(kb),
            cognitive_style=profile.get("cognitive_style", "未知"),
            difficulty=difficulty,
            topic=topic,
            count=question_count,
        ) + ref_block

        # 画像引导注入 — 新用户首次使用时收集画像
        from app.core.shared_utils import _build_profile_guide
        profile_guide = _build_profile_guide(profile)
        if profile_guide:
            question_system += profile_guide

        # 携带对话历史上下文，确保多轮对话中约束条件和语言偏好跨轮传递
        from app.core.shared_utils import _build_llm_messages
        all_msgs = state.get("messages", [])
        messages = _build_llm_messages(
            question_system,
            all_msgs,
            last_msg,
            max_history=12,
            topic_context=topic_ctx,
        )

        from app.utils.llm_helper import truncate_messages
        messages = truncate_messages(messages, max_tokens=6000)

        # 统一走 stream_pending 流式管线：Agent 只准备 messages，不自行调用 LLM
        # _bridge_stream 在 chat.py 中负责 true streaming（逐 chunk yield）
        # 完整题目文本由 chat.py 在流式完成后通过 cache_questions_text() 写入缓存
        return {
            "current_agent": "question_agent",
            "stream_buffer": "",
            "agent_outputs": {
                **state.get("agent_outputs", {}),
                "question_agent": {
                    "mode": "generate",
                    "difficulty": difficulty,
                    "topic": topic,
                    "question_count": question_count,
                    "last_questions_text": "",   # 由 chat.py 流式完成后缓存填充
                    "bkt_p_known": tracker.get_or_create(topic).p_known,
                    "stream_pending": {
                        "messages": messages,
                        "temperature": 0.6,
                        "max_tokens": 4096,
                        "use_safe": True,    # 启用 LLM 重试保护
                        "chunk_size": 2,     # 逐字打字机效果
                    },
                },
            },
        }


def parse_grading_result(grading_text: str) -> dict:
    """解析 LLM 批改回复，提取每道题的正误判定。

    GRADE_PROMPT 预期输出格式：
        ### 第 N 题：正确/错误
        [具体反馈...]
        ### 本轮成绩
        - 正确率：X/Y（XX%）

    支持变体：全角/半角冒号、中文"正确/错误"、勾叉符号、题号前 ## 数量变化。

    Returns:
        {"per_question": [True, False, True], "correct_count": 2, "total_count": 3}
        per_question 为空时说明解析失败（LLM 未按格式输出）。
    """
    per_question = []
    correct_count = 0
    total_count = 0

    # 主模式: "### 第 N 题：正确" 或 "### 第 N 题：错误"
    # 兼容 ##/###、全角/半角冒号、中英文标记
    pattern = r'#{2,4}\s*第\s*(\d+)\s*题\s*[：:]\s*(正确|错误|[✓✗✅❌]|对|错)'
    matches = re.findall(pattern, grading_text)

    if matches:
        seen = set()
        # 按题号排序，去重
        matches_sorted = sorted(matches, key=lambda x: int(x[0]))
        for qnum_str, result in matches_sorted:
            qnum = int(qnum_str)
            if qnum in seen:
                continue
            seen.add(qnum)
            is_correct = result in ('正确', '✓', '对', '✅')
            per_question.append(is_correct)
            if is_correct:
                correct_count += 1
            total_count += 1
    else:
        # 回退: 解析汇总行 "正确率：X/Y" 或 "X/Y（XX%）"
        summary = re.search(r'正确率[：:]\s*(\d+)\s*/\s*(\d+)', grading_text)
        if not summary:
            summary = re.search(r'[（(]\s*(\d+)\s*/\s*(\d+)\s*[）)]', grading_text)
        if not summary:
            summary = re.search(r'(\d+)\s*/\s*(\d+)\s*[（(]\s*\d+%', grading_text)
        if summary:
            correct_count = int(summary.group(1))
            total_count = int(summary.group(2))
            # 无法得知具体哪题对错，按比例构造
            per_question = [True] * correct_count + [False] * (total_count - correct_count)

    return {
        "per_question": per_question,
        "correct_count": correct_count,
        "total_count": total_count,
    }
