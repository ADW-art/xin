"""
共享工具函数 —— 纯数据转换，无数据库依赖

提取自 chat.py 和 profile_agent.py，消除循环导入。
所有函数均为纯函数（无副作用、无DB依赖），可被任何模块安全导入。
"""
import re
import logging
from langchain_core.messages import HumanMessage, AIMessage

logger = logging.getLogger(__name__)


# ============================================================
# 从 chat.py 提取
# ============================================================


def _normalize_concept_name(raw: str) -> str:
    """将原始文本规范化为标准知识点名词（BKT节点名）

    只返回真正的学科/技术知识点名词，绝不返回功能分类名！
    如果无法从输入中提取到有效的知识点名词，统一返回 "未分类"。
    """
    if not raw:
        return "未分类"


    text = raw.strip()
    text_lower = text.lower()

    # ═══════════ 层级1：编程语言（最高优先级，精确匹配） ═══════════
    LANG_MAP = {
        "c++": "C++基础", "cpp": "C++基础", "c#": "C#基础",
        "python": "Python基础", "java": "Java基础",
        "go": "Go语言", "golang": "Go语言",
        "javascript": "JavaScript", "js": "JavaScript",
        "rust": "Rust语言", "swift": "Swift语言",
        "typescript": "TypeScript", "ts": "TypeScript",
        "kotlin": "Kotlin语言", "ruby": "Ruby语言",
        "php": "PHP语言", "c语言": "C语言基础", "c 语言": "C语言基础",
        "sql": "SQL数据库", "html": "HTML基础", "css": "CSS基础",
    }
    for kw, name in LANG_MAP.items():
        if kw in text_lower:
            return name

    # ═══════════ 层级2：数据结构与算法概念 ═══════════
    DS_KEYWORDS = {
        "react": "React框架", "vue": "Vue框架", "angular": "Angular框架",
        "node.js": "Node.js", "nodejs": "Node.js",
        "pytorch": "PyTorch框架", "tensorflow": "TensorFlow框架",
        "pandas": "Pandas数据分析", "numpy": "NumPy科学计算",
        "matplotlib": "Matplotlib可视化", "scikit-learn": "Scikit-learn",
        "webpack": "Webpack构建", "vite": "Vite构建工具",
        "dom": "DOM操作",
        "链表": "链表", "单链表": "链表", "双链表": "链表", "循环链表": "链表",
        "栈": "栈", "堆栈": "栈", "队列": "队列", "双端队列": "队列",
        "哈希": "哈希表", "hash": "哈希表", "散列": "哈希表",
        "二叉树": "二叉树", "平衡树": "平衡二叉树", "红黑树": "红黑树",
        "b树": "B树", "b+树": "B+树", "avl": "AVL树",
        "树": "树结构", "图": "图论", "有向图": "图论", "无向图": "图论",
        "数组": "数组", "矩阵": "矩阵运算", "位运算": "位操作",
        "集合": "集合", "映射": "映射", "堆": "堆", "优先队列": "优先队列",
        "并查集": "并查集", "线段树": "线段树", "字典树": "字典树(Trie)",
        "跳表": "跳表",
        "排序": "排序算法", "冒泡": "冒泡排序", "快速排序": "快速排序", "快排": "快速排序",
        "归并排序": "归并排序", "堆排序": "堆排序", "桶排序": "桶排序", "计数排序": "计数排序",
        "查找": "查找算法", "二分查找": "二分查找", "二分": "二分查找",
        "递归": "递归算法", "回溯": "回溯算法", "dfs": "深度优先搜索(DFS)",
        "bfs": "广度优先搜索(BFS)", "动态规划": "动态规划", "dp": "动态规划",
        "贪心": "贪心算法", "分治": "分治算法",
        "最短路": "最短路径算法", "最小生成树": "最小生成树", "拓扑排序": "拓扑排序",
        "双指针": "双指针技巧", "滑动窗口": "滑动窗口", "前缀和": "前缀和",
        "单调栈": "单调栈", "单调队列": "单调队列",
        "指针": "指针", "引用": "引用", "地址": "指针",
        "列表": "列表(List)", "字典": "字典(Dict)", "元组": "元组(Tuple)",
        "集合(set)": "集合(Set)", "切片": "切片(Slice)",
        "函数": "函数", "方法": "方法", "闭包": "闭包",
        "类": "类与对象", "对象": "类与对象", "实例": "类与对象",
        "面向对象": "面向对象编程", "oop": "面向对象编程",
        "继承": "继承", "多态": "多态", "封装": "封装",
        "虚函数": "虚函数", "重载": "重载", "重写": "重写",
        "模板": "模板编程", "泛型": "泛型编程", "stl": "STL容器",
        "装饰器": "装饰器", "推导式": "推导式", "生成器": "生成器",
        "迭代器": "迭代器", "上下文管理器": "上下文管理器",
        "协程": "协程", "异步": "异步编程", "并发": "并发编程",
        "线程": "多线程", "进程": "进程管理", "锁": "锁机制",
        "异常": "异常处理", "错误处理": "异常处理",
        "内存": "内存管理", "垃圾回收": "垃圾回收(GC)",
        "字符串": "字符串处理", "正则": "正则表达式",
        "文件": "文件操作", "io": "IO操作", "网络编程": "网络编程",
        "http": "HTTP协议", "api": "API设计", "rest": "RESTful API",
        "数据库": "数据库", "mysql": "MySQL",
        "redis": "Redis", "mongodb": "MongoDB", "orm": "ORM框架",
        "事件": "事件处理", "组件": "组件化开发",
        "机器学习": "机器学习", "深度学习": "深度学习",
        "神经网络": "神经网络", "卷积": "CNN", "循环网络": "RNN/LSTM",
        "nlp": "自然语言处理", "cv": "计算机视觉",
        "强化学习": "强化学习", "transformer": "Transformer模型",
        "大语言模型": "大语言模型", "llm": "大语言模型",
    }
    for kw, name in DS_KEYWORDS.items():
        if kw in text_lower or kw in text:
            return name

    # ═══════════ 层级3：技术领域/方向 ═══════════
    DOMAIN_KEYWORDS = {
        "前端": "前端开发", "后端": "后端开发", "全栈": "全栈开发",
        "移动端": "移动端开发", "app": "App开发", "小程序": "小程序开发",
        "嵌入式": "嵌入式开发", "系统编程": "系统编程",
        "DevOps": "DevOps运维", "devops": "DevOps运维",
        "云计算": "云计算", "docker": "Docker容器化", "kubernetes": "K8s编排",
        "微服务": "微服务架构", "分布式": "分布式系统",
        "设计模式": "设计模式", "架构": "软件架构",
        "测试": "软件测试", "自动化测试": "自动化测试",
        "安全": "网络安全", "密码学": "密码学",
        "操作系统": "操作系统", "编译原理": "编译原理",
        "计算机网络": "计算机网络", "数据科学": "数据科学",
        "数据分析": "数据分析", "数据挖掘": "数据挖掘",
        "面试": "面试准备", "leetcode": "LeetCode刷题", "力扣": "LeetCode刷题",
        "项目": "项目实战", "开源": "开源项目",
        "git": "Git版本控制", "linux": "Linux系统",
        "shell": "Shell脚本", "bash": "Bash脚本",
    }
    for kw, name in DOMAIN_KEYWORDS.items():
        if kw in text_lower or kw in text:
            return name

    return "未分类"


# ============================================================
# 从 profile_agent.py 提取
# ============================================================

def _structure_knowledge_base(raw_text: str) -> dict:
    """将用户自由文本解析为结构化的知识点-分数 dict"""
    topics = [t.strip() for t in re.split(r"[,，、;；/]", raw_text) if t.strip()]
    if not topics:
        return {}
    result: dict[str, float] = {}
    advanced_kw = ["精通", "熟练", "熟悉", "3年", "5年", "多年", "工作", "项目"]
    beginner_kw = ["入门", "初学", "零基础", "没学过", "刚开始", "了解一点", "基础"]
    is_advanced = any(kw in raw_text for kw in advanced_kw)
    is_beginner = any(kw in raw_text for kw in beginner_kw)
    for topic in topics:
        if not topic or len(topic) < 2:
            continue
        base = 70.0 if is_advanced else (35.0 if is_beginner else 55.0)
        detail_bonus = min(15, len(topic) - 2) * 1.5
        result[topic] = round(min(95, max(20, base + detail_bonus)), 1)
    return result


# ============================================================
# 画像状态分析 — supervisor 和 chat_agent 共用
# ============================================================

# 画像维度定义（模块级常量，_get_profile_status 和 _build_profile_guide 共享）
# 对齐 DB LearningProfile 模型实际字段 (7维)
_ALL_PROFILE_DIMS = ["knowledge_base", "cognitive_style", "learning_goal",
                     "weekly_hours", "preferred_resource_type", "error_patterns",
                     "dimension_scores"]
_ALL_PROFILE_DIM_LABELS = {
    "knowledge_base": "知识基础", "cognitive_style": "认知风格",
    "learning_goal": "学习目标", "weekly_hours": "每周时间",
    "preferred_resource_type": "偏好资源", "error_patterns": "易错模式",
    "dimension_scores": "能力维度",
}


def _get_profile_status(profile: dict | None) -> tuple[list[str], list[str]]:
    """分析画像填写状态，返回 (已填维度列表, 未填维度列表)

    改进版：正确处理空 dict (knowledge_base={})、零值、空字符串等边界情况。
    供 supervisor、chat_agent 等模块共享使用。
    """
    profile = profile or {}

    def _is_filled(val) -> bool:
        if val is None:
            return False
        if isinstance(val, str) and val.strip() == "":
            return False
        if isinstance(val, dict) and len(val) == 0:
            return False
        if isinstance(val, (int, float)) and val == 0:
            return False
        return True

    filled = [_ALL_PROFILE_DIM_LABELS[k] for k in _ALL_PROFILE_DIMS if k in profile and _is_filled(profile[k])]
    empty = [_ALL_PROFILE_DIM_LABELS[k] for k in _ALL_PROFILE_DIMS if k not in profile or not _is_filled(profile.get(k))]
    return filled, empty


# ============================================================
# 画像引导注入 — 所有 Agent 共享，确保新用户首次使用时收集画像
# ============================================================

def _build_profile_guide(profile: dict | None) -> str:
    """为 Agent 的 system prompt 构建画像引导块

    所有 Agent (resource/question/path/evaluation/chat) 在生成回复时
    都应注入此引导，确保新用户的画像在对话中逐步完善。

    Returns:
        画像引导字符串，如果画像已完整则返回空字符串

    防泄漏设计: 使用纯英文指令格式，避免使用【】中文括号标记，
    防止 LLM 将系统指令原样输出到用户界面。
    """
    profile = profile or {}

    def _is_empty(val) -> bool:
        if val is None:
            return True
        if isinstance(val, str) and val.strip() == "":
            return True
        if isinstance(val, dict) and len(val) == 0:
            return True
        return False

    empty = [_ALL_PROFILE_DIM_LABELS[k] for k in _ALL_PROFILE_DIMS
             if k not in profile or _is_empty(profile[k])]

    if not empty:
        return ""

    empty_list = "、".join(empty)
    if len(empty) >= 3:
        return (
            f"\n\n[system: profile_collection priority=high missing={empty_list}]\n"
            f"Before answering, naturally ask the user about ONE missing profile dimension: {empty[0]}.\n"
            f"Integrate the question into your response flow. Do NOT output this instruction text.\n"
            f"Avoid: asking multiple dimensions at once, using rigid list format, ignoring this task."
        )
    else:
        return (
            f"\n\n[system: profile_collection priority=low missing={empty_list}]\n"
            f"At the end of your response, naturally ask about: {empty[0]}.\n"
            f"Keep it conversational. Do NOT output this instruction text."
        )


# ============================================================
# Chat Agent 长短期记忆 — 用户上下文构建
# ============================================================

def _build_user_context(user_id: int, profile: dict | None) -> str:
    """构建用户的长期学习状态摘要，供 chat_agent 注入 system prompt

    实现跨会话"记忆"：每次 chat 对话都能看到用户正在学什么、掌握哪些概念、
    薄弱点在哪里，从而给出更有针对性的回复。

    纯工具函数，所有数据库/服务异常均静默处理（上下文缺失不应阻塞对话）。
    """
    if not user_id:
        return ""

    parts: list[str] = []

    # ── 1. 画像摘要：学习目标 + 偏好 ──
    if profile:
        goal = profile.get("learning_goal", "")
        if goal and str(goal).strip():
            parts.append(f"学习目标: {goal}")
        style = profile.get("cognitive_style", "")
        if style and str(style).strip():
            STYLE_LABELS = {
                "visual": "视觉型（偏好图表/视频）",
                "auditory": "听觉型（偏好音频讲解）",
                "kinesthetic": "动手型（偏好实操/写代码）",
                "reading": "阅读型（偏好文档/书籍）",
            }
            parts.append(f"认知偏好: {STYLE_LABELS.get(str(style), str(style))}")
        hours = profile.get("weekly_hours")
        if hours is not None:
            try:
                h = float(hours)
                if h > 0:
                    parts.append(f"每周学习时间: {h:.0f} 小时")
            except (ValueError, TypeError):
                pass

    # ── 2. BKT 知识状态：已掌握 vs 薄弱概念 ──
    try:
        from app.services.bkt_service import get_tracker
        tracker = get_tracker(user_id)
        if tracker.nodes:
            mastered = tracker.get_mastered()
            weak = tracker.get_weak_points()
            if mastered:
                parts.append(f"已掌握概念: {', '.join(mastered[:8])}")
            if weak:
                parts.append(f"薄弱概念: {', '.join(weak[:8])}")
    except Exception as e:
        logger.warning("BKT state collection failed for user %s: %s", user_id, e)
        pass

    # ── 3. 近期学习活动：从对话历史提取关注主题 ──
    try:
        from app.core.database import get_session
        from app.models.conversation import Conversation
        with get_session() as db:
            recent = (
                db.query(Conversation)
                .filter(
                    Conversation.user_id == user_id,
                    Conversation.role == "user",
                )
                .order_by(Conversation.created_at.desc())
                .limit(10)
                .all()
            )
            topics: set[str] = set()
            INTEREST_KEYWORDS = [
                "Python", "Java", "C++", "Go", "Rust", "JavaScript",
                "TypeScript", "React", "Vue", "Spring", "Django",
                "算法", "数据结构", "数据库", "网络", "前端", "后端",
                "机器学习", "深度学习", "操作系统", "Linux", "Docker",
                "设计模式", "面试", "LeetCode",
            ]
            for c in recent:
                content = c.content or ""
                for word in INTEREST_KEYWORDS:
                    if word.lower() in content.lower():
                        topics.add(word)
            if topics:
                parts.append(f"近期关注: {', '.join(sorted(topics)[:8])}")
    except Exception as e:
        logger.warning("Conversation history query failed for user %s: %s", user_id, e)
        pass

    if not parts:
        return ""

    return "## 学生当前状态\n" + "\n".join(f"- {p}" for p in parts) + "\n"


# ============================================================
# 从 chat.py 提取 — Supervisor 也使用
# ============================================================

def _build_llm_messages(
    system_prompt: str,
    state_messages: list,
    current_content: str,
    max_history: int = 8,
    topic_context: dict | None = None,
) -> list[dict]:
    """构建带历史上下文的 LLM 消息列表

    关键设计：
    - state_messages 是 LangGraph 的完整消息历史（包含当前用户消息）
    - 当前用户消息总是在 state_messages 末尾，由 current_content 显式追加
    - 避免重复：如果 state_messages 末尾消息与 current_content 相同，从历史中排除
    """
    msgs = [{"role": "system", "content": system_prompt}]
    if topic_context and (topic_context.get("current_topic") or topic_context.get("domain") or topic_context.get("user_language")):
        context_hint = "\n\n## 当前对话上下文（必须严格遵守）"
        if topic_context.get("user_language"):
            context_hint += f"\n- **用户指定的编程语言：{topic_context['user_language']}**（所有代码示例、题目、讲解必须使用此语言，绝对不能使用其他语言）"
        if topic_context.get("domain"):
            context_hint += f"\n- 讨论领域：{topic_context['domain']}"
        if topic_context.get("current_topic"):
            context_hint += f"\n- 当前主题：{topic_context['current_topic']}"
        if topic_context.get("user_constraints"):
            constraints = "、".join(topic_context["user_constraints"])
            context_hint += f"\n- **用户明确排除/不想要的内容：{constraints}（绝对不要涉及这些内容）"
        if topic_context.get("pronoun_map"):
            mappings = ", ".join(f'"{k}"->"{v}"' for k, v in topic_context['pronoun_map'].items())
            context_hint += f"\n- 代词指代：{mappings}"
        msgs[0]["content"] += context_hint

    # 取最近的 max_history 条历史消息
    raw_history = state_messages[-max_history:] if len(state_messages) > max_history else list(state_messages)

    # 避免重复：如果 raw_history 末尾正好是当前用户消息，从历史中排除它
    # （当前消息将通过 current_content 在末尾追加）
    if raw_history:
        try:
            last_content = str(getattr(raw_history[-1], 'content', ''))
        except Exception:
            last_content = ''
        if last_content.strip() == current_content.strip():
            raw_history = raw_history[:-1]

    # 将 LangChain 消息类型转换为标准的 {"role": ..., "content": ...} 格式
    # 注意: content 可能是 str 或 list[dict]（多模态消息含图片base64），list 直接保留
    for msg in raw_history:
        msg_type = type(msg).__name__
        # Issue 3 Fix: 兼容 LangGraph checkpoint 恢复后 messages 元素可能为 dict
        # dict 没有 .content 属性，必须用 msg.get("content", "") 兜底
        content_val = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        if isinstance(content_val, list):
            formatted_content = content_val  # 多模态格式，直接保留
        else:
            formatted_content = str(content_val)
            # Issue 1 Fix: 清理可能泄漏到对话历史中的 HTML 语法高亮标记
            # 如果 LLM 之前生成过含 <span class="sk"> 等的代码，这些标记会进入
            # 下一轮对话的上下文，形成自我强化的污染循环。
            # 此处做防御性清理，确保发送给 LLM 的对话历史是干净的纯文本/Markdown。
            formatted_content = _clean_llm_context(formatted_content)
        if isinstance(msg, HumanMessage):
            msgs.append({"role": "user", "content": formatted_content})
        elif isinstance(msg, AIMessage):
            msgs.append({"role": "assistant", "content": formatted_content})
        # 兼容 SystemMessage 等其他类型（如有）
        elif 'System' in msg_type:
            pass  # system prompt 已由 system_prompt 参数提供，不重复

    # 追加当前用户消息（核心输入），也做清理
    cleaned_current = _clean_llm_context(str(current_content)) if isinstance(current_content, str) else current_content
    msgs.append({"role": "user", "content": cleaned_current})
    return msgs


def _clean_llm_context(text: str) -> str:
    """防御性清理：剥离可能泄露到 LLM 上下文中的 HTML 语法高亮残渣

    前端 ChatMessage.vue 的 highlightCode() 使用 <span class="sk/sf/sc/sd/ss/sn">
    做语法着色。如果这些标记通过任何路径进入对话历史（用户粘贴渲染后的代码、
    LLM 自产生标记等），会在下一轮对话上下文中形成污染循环。

    此函数剥离所有 HTML 标签和孤立的 CSS class 片段，
    确保 LLM 收到的对话历史只包含纯 Markdown 文本。
    """
    if not isinstance(text, str):
        return text
    # Step 1: 移除完整的 HTML span/div 标签
    cleaned = re.sub(r'<span\b[^>]*>', '', text)
    cleaned = re.sub(r'</span>', '', cleaned)
    cleaned = re.sub(r'<div\b[^>]*>', '', cleaned)
    cleaned = re.sub(r'</div>', '', cleaned)
    cleaned = re.sub(r'<code\b[^>]*>', '', cleaned)
    cleaned = re.sub(r'</code>', '', cleaned)
    cleaned = re.sub(r'<pre\b[^>]*>', '', cleaned)
    cleaned = re.sub(r'</pre>', '', cleaned)
    # Step 2: 移除 HTML 实体编码的 span 标签（&lt;span ... &gt;）
    cleaned = re.sub(r'&lt;span\b[^&]*&gt;', '', cleaned)
    cleaned = re.sub(r'&lt;/span&gt;', '', cleaned)
    # Step 3: 移除孤立的 CSS class 属性片段（如 "sc"> "sk"> "sf"> "sd"> "ss"> "sn">）
    # 注意: 不加 \b 锚定, 因为 artifact 前通常是非单词字符 (空格/: /;/>)
    cleaned = re.sub(r'"[a-z]{2,4}">', '', cleaned)
    # Step 4: 移除孤立的 class="xx" 属性
    cleaned = re.sub(r'\s*class\s*=\s*\b"[a-z]{2,4}"\b', '', cleaned)
    return cleaned


# ═══════════════════════════════════════════════════════════════
# 教学继续检测 (chat.py + supervisor.py 共享)
# ═══════════════════════════════════════════════════════════════

_CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
           '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15, '十六': 16, '十七': 17,
           '十八': 18, '十九': 19, '二十': 20, '二十一': 21, '二十二': 22, '二十三': 23,
           '二十四': 24, '二十五': 25, '二十六': 26, '二十七': 27, '二十八': 28,
           '二十九': 29, '三十': 30}


_CN_DIGIT = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
_CN_TENS = {'十': 10, '二十': 20, '三十': 30, '四十': 40, '五十': 50, '六十': 60, '七十': 70, '八十': 80, '九十': 90}


def _parse_cn_number(num_str: str) -> int:
    """解析中文数字为整数, 支持 1-99.
    P2-FIX: 替代硬编码 _CN_NUM dict, 支持 31-99 的复合数字.
    """
    if not num_str:
        return 0
    if num_str.isdigit():
        return int(num_str)
    # 先查硬编码表 (含特殊项如"十一")
    cached = _CN_NUM.get(num_str)
    if cached is not None:
        return cached
    # 复合中文数字: "三十一" → 30 + 1 = 31
    total = 0
    for tens_word, tens_val in sorted(_CN_TENS.items(), key=lambda x: -len(x[0])):
        if num_str.startswith(tens_word):
            total += tens_val
            num_str = num_str[len(tens_word):]
            break
    for digit_word, digit_val in _CN_DIGIT.items():
        if num_str == digit_word:
            total += digit_val
            break
    return total if total > 0 else 0


def _parse_day_number(text: str) -> int | None:
    """从文本中提取第X天的数字索引(0-based)"""
    m = re.search(r'第\s*([一二三四五六七八九十\d]+)\s*(天|节|课|章|节点|步|阶段)', text)
    if not m:
        return None
    num_str = m.group(1)
    num = _parse_cn_number(num_str)
    return num - 1 if num > 0 else None


def _fuzzy_match_path_node(text: str, active_path: list[str]) -> tuple:
    """对 active_path 做 jieba+Jaccard 模糊匹配，返回 (best_idx, best_score, best_node)

    参考 Open Agent School: jieba 分词做中文首选，SequenceMatcher 做短文本兜底
    """
    import jieba
    from difflib import SequenceMatcher

    _clean_pattern = re.compile(r'第[一二三四五六七八九十\d]+\s*天\s*[-–—]\s*第[一二三四五六七八九十\d]+\s*天[：:]\s*')
    # P0-FIX (2026-07-12): active_path 元素可能是 dict {"topic": "..."} 或纯字符串
    def _node_text(n):
        if isinstance(n, dict):
            return n.get("topic", n.get("name", str(n)))
        return str(n)
    clean_nodes = [_clean_pattern.sub('', _node_text(n)).strip() for n in active_path]

    text_lower = text.lower().strip()
    text_tokens = set(jieba.lcut(text_lower))

    best_idx = None
    best_score = 0.0
    best_node = ""

    for i, node in enumerate(clean_nodes):
        node_lower = node.lower()
        node_tokens = set(jieba.lcut(node_lower))
        if text_tokens and node_tokens:
            jaccard = len(text_tokens & node_tokens) / len(text_tokens | node_tokens)
        else:
            jaccard = 0.0

        seq_ratio = SequenceMatcher(None, text_lower, node_lower).ratio()
        combined = jaccard * 0.6 + seq_ratio * 0.4

        if combined > best_score:
            best_score = combined
            best_idx = i
            best_node = active_path[i]

    return best_idx, best_score, best_node


def is_teaching_continue(text: str, tc: dict | None = None) -> bool:
    """判断用户消息是否为教学流程的继续信号 (chat.py + supervisor.py 共用)

    多级检测:
      1. 精确继续词
      2. "第X天" 导航模式
      3. 自然语言引用 active_path 中的节点名
    """
    stripped = text.strip()
    short_continue = re.match(
        r'^(好|好的|可以|行|来|开始|没问题|嗯|OK|ok|yes|是|对|继续|下一个|下一节|接着|继续学|接着学|往下|往下学|学下一个|go on|next|continue|sure|yep|yeah|当然|必须的|搞起|来吧|开始吧|继续吧|OK吧)$',
        stripped
    )
    if short_continue:
        return True
    if re.search(r'(开始|讲解|讲一下|学一下|详细|进入|说说|讲).*第[一二三四五六七八九十\d]+', stripped):
        return True
    if re.search(r'第[一二三四五六七八九十\d]+\s*(天|节|课|章|节点|步)', stripped):
        return True
    if len(stripped) <= 10 and any(kw in stripped for kw in ["继续", "下一个", "接着", "往下", "go on", "next"]):
        return True
    if tc and len(stripped) >= 4:
        active_path = tc.get("active_path", [])
        if len(active_path) >= 2:
            _best_idx, _best_score, _ = _fuzzy_match_path_node(stripped, active_path)
            if _best_idx is not None and _best_score >= 0.4:
                logger.info("is_teaching_continue: 模糊匹配节点 (score=%.2f)", _best_score)
                return True
    return False


def resolve_teaching_reference(text: str, tc: dict) -> dict | None:
    """将教学导航引用解析为 active_path 中的实际知识点名 (supervisor.py 共用)

    多策略级联:
      1. 精确 "第X天" 解析
      2. jieba 分词 + Jaccard 相似度
      3. SequenceMatcher 字符相似度
    """
    active_path = tc.get("active_path", [])
    if not active_path:
        return None

    idx = _parse_day_number(text)
    if idx is not None and 0 <= idx < len(active_path):
        node = active_path[idx]
        logger.info("resolve_teaching_reference: '%s' -> [%d]='%s'", text.strip()[:30], idx, node)
        return {"topic": node, "index": idx}

    if len(active_path) >= 2 and len(text.strip()) >= 4:
        _best_idx, _best_score, _best_node = _fuzzy_match_path_node(text, active_path)
        if _best_idx is not None and _best_score >= 0.4:
            logger.info(
                "resolve_teaching_reference: 模糊匹配 '%s' -> [%d]='%s' (score=%.2f)",
                text.strip()[:40], _best_idx, _best_node, _best_score,
            )
            return {"topic": _best_node, "index": _best_idx}

    return None
