"""
对话上下文服务 — 从 chat.py 提取, 照搬 OpenSpawn BusBackend Protocol 单一职责原则

提供:
  - 用户画像加载
  - 对话历史加载
  - 话题上下文提取 (语言偏好/领域/约束/代词映射)

纯数据转换, 无副作用 (除 DB 读取外)。
"""

import re
import logging

from app.core.database import get_session
from app.models.profile import LearningProfile
from app.models.conversation import Conversation

logger = logging.getLogger(__name__)


def load_user_profile(user_id: int) -> dict | None:
    """从 MySQL 加载用户画像 — supervisor.py + chat.py 共用"""
    if not user_id:
        return None
    with get_session() as db:
        row = db.query(LearningProfile).filter(LearningProfile.user_id == user_id).first()
        if not row:
            return None
        return {
            "knowledge_base": row.knowledge_base,
            "cognitive_style": row.cognitive_style,
            "learning_goal": row.learning_goal,
            "weekly_hours": row.weekly_hours,
            "error_patterns": row.error_patterns,
            "preferred_resource_type": row.preferred_resource_type,
            "dimension_scores": row.dimension_scores,
        }


def load_conversation_history(user_id: int, limit: int = 24) -> list:
    """加载最近的对话历史，构建 LangChain messages 列表"""
    if not user_id:
        return []
    with get_session() as db:
        rows = (
            db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .all()
        )
        rows.reverse()
        from langchain_core.messages import HumanMessage, AIMessage
        messages = []
        for row in rows:
            if row.role == "user":
                messages.append(HumanMessage(content=row.content))
            else:
                messages.append(AIMessage(content=row.content))
        return messages


def extract_topic_context(history_msgs: list, current_msg: str) -> dict:
    """从对话历史中提取当前话题上下文

    Returns dict with keys:
        current_topic, recent_topics, pronoun_map, domain,
        user_language, user_constraints
    """
    result = {
        "current_topic": "",
        "recent_topics": [],
        "pronoun_map": {},
        "domain": "",
        "user_language": "",
        "user_constraints": [],
    }
    if not history_msgs:
        return result
    all_text = current_msg + " "
    for msg in history_msgs[-8:]:
        content = str(getattr(msg, 'content', msg))
        all_text += content + " "
    language_patterns = [
        r'(?:我要学|想学|学|用|写|教我|帮我|给我)[\s]*([Cc][+\#]*|[Gg]o|[Rr]ust|[Jj]ava[Ss]cript|[Pp]ython|[Jj]ava|[Ss]wift|[Kk]otlin|[Rr]uby|[Pp]hp|[Tt]ype[Ss]cript)',
        r'(?:用|使用|基于|基于?)[\s]*([Cc][+\#]+|[Gg]o|[Rr]ust|[Jj]ava[Ss]cript|[Pp]ython|[Jj]ava)',
        r'([Cc]\+\+|[Cc]#|[Gg]o|[Rr]ust|[Pp]ython|[Jj]ava|[Jj]ava[Ss]cript|[Ss]wift|[Kk]otlin)(?:语言|开发|编程)?',
    ]
    for pattern in language_patterns:
        m = re.search(pattern, all_text)
        if m and m.lastindex and m.lastindex >= 1:
            lang = m.group(1).strip()
            if lang and len(lang) >= 2:
                result["user_language"] = lang
                break
    exclude_patterns = [
        r'(?:不要|别|不用|不要给我|不想|排除|跳过)[\s]*(.{2,10}?)(?:[，。！？\s]|$)',
    ]
    for pattern in exclude_patterns:
        matches = re.findall(pattern, all_text)
        for m2 in matches:
            m2 = m2.strip()
            if len(m2) >= 2:
                result["user_constraints"].append(m2)
    domain_keywords = {
        "C++基础": ["c++", "cpp", "指针", "引用", "内存管理", "模板", "STL", "面向对象", "虚函数", "多态", "继承"],
        "Python基础": ["python", "列表", "字典", "元组", "函数", "类", "装饰器", "推导式", "迭代器", "生成器"],
        "Java基础": ["java", "spring", "maven", "jvm", "集合", "stream", "注解", "接口", "抽象类"],
        "Go语言": ["go", "goroutine", "channel", "协程", "并发", "interface", "struct", "slice", "map"],
        "JavaScript": ["javascript", "js", "node", "react", "vue", "angular", "promise", "async", "dom"],
        "数据结构": ["树", "图", "链表", "栈", "队列", "哈希", "排序", "查找", "二叉树", "红黑树", "B树", "数组"],
        "算法": ["递归", "动态规划", "贪心", "分治", "回溯", "DFS", "BFS", "二分", "快排", "归并"],
        "数据库": ["SQL", "MySQL", "索引", "事务", "JOIN", "查询优化", "NoSQL", "Redis", "PostgreSQL"],
        "前端开发": ["HTML", "CSS", "JavaScript", "React", "Vue", "DOM", "组件", "响应式", "CSS3"],
        "后端开发": ["API", "REST", "Flask", "Django", "Spring", "微服务", "接口", "认证", "中间件"],
        "机器学习": ["神经网络", "深度学习", "训练", "模型", "特征", "分类", "回归", "聚类", "TensorFlow", "PyTorch"],
    }
    domain_scores = {}
    for domain, keywords in domain_keywords.items():
        score = sum(1 for kw in keywords if kw.lower() in all_text.lower())
        if score >= 1:
            domain_scores[domain] = score
    if result["user_language"]:
        lang_lower = result["user_language"].lower()
        for domain in domain_keywords:
            if lang_lower in domain.lower() or any(kw.lower() == lang_lower for kw in domain_keywords[domain]):
                result["domain"] = domain
                break
        if not result["domain"] and domain_scores:
            result["domain"] = max(domain_scores, key=domain_scores.get)
    elif domain_scores:
        result["domain"] = max(domain_scores, key=domain_scores.get)
    topic_patterns = [
        r'(?:[Cc]\+\+|[Pp]ython|[Jj]ava|[Gg]o|[Jj]avascript)[\s]*(?:的)?[\s]*(?:列表|字典|数组|字符串|函数|类|指针|引用|容器|模板|迭代器|STL|集合|对象|变量|循环|条件|异常|内存|线程|并发|协程)',
        r'(?:二叉|平衡|红黑|B[\s]*树|AVL|堆|线段| Trie |前缀)*树',
        r'(?:快速|归并|冒泡|插入|选择|桶|基数|希尔|计数)*排序',
        r'(链表|栈|队列|哈希表|散列表|堆栈|数组|矩阵|图|有向图|无向图)',
        r'(递归|迭代|遍历|搜索|查找|回溯|贪心|分治|动态规划|DFS|BFS|二分|双指针|滑动窗口)',
        r'(指针|引用|虚函数|纯虚函数|模板|特化|偏特化|STL|vector|map|set|智能指针|unique_ptr|shared_ptr|移动语义|右值引用)',
        r'(装饰器|推导式|生成器|迭代器|闭包|lambda|切片|解包|上下文管理符|元类|描述符|@property)',
        r'(封装|继承|多态|重载|覆盖|抽象|接口|泛型|类型推断|内存管理|垃圾回收|并发|并行|异步|回调|Promise)',
    ]
    topics_found = []
    for pattern in topic_patterns:
        matches = re.findall(pattern, all_text, re.IGNORECASE)
        for m3 in matches:
            if isinstance(m3, tuple):
                m3 = m3[0]
            m3 = m3.strip()
            if len(m3) >= 2 and len(m3) <= 20 and m3 not in topics_found:
                topics_found.append(m3)
    if result["user_language"] and result["user_language"] not in topics_found:
        topics_found.append(result["user_language"])
    if topics_found:
        result["current_topic"] = topics_found[-1]
        result["recent_topics"] = topics_found[-5:]
    pronouns = ["它", "这个", "这个概念", "那个", "那", "这种"]
    if result["current_topic"]:
        for pronoun in pronouns:
            if pronoun in current_msg:
                result["pronoun_map"][pronoun] = result["current_topic"]
                break
    return result
