"""
共享工具函数 —— 纯数据转换，无数据库依赖

提取自 chat.py 和 profile_agent.py，消除循环导入。
所有函数均为纯函数（无副作用、无DB依赖），可被任何模块安全导入。
"""
import re
import logging

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
        "数据库": "数据库", "sql": "SQL数据库", "mysql": "MySQL",
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
    for msg in raw_history:
        msg_type = type(msg).__name__
        if 'Human' in msg_type:
            msgs.append({"role": "user", "content": str(msg.content)})
        elif 'AI' in msg_type:
            msgs.append({"role": "assistant", "content": str(msg.content)})
        # 兼容 SystemMessage 等其他类型（如有）
        elif 'System' in msg_type:
            pass  # system prompt 已由 system_prompt 参数提供，不重复

    # 追加当前用户消息（核心输入）
    msgs.append({"role": "user", "content": current_content})
    return msgs
