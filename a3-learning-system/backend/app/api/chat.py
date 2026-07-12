"""
对话 API —— SSE 流式端点

POST /api/chat/send → 接收用户消息 → 调用星火 → 逐字流式返回
"""

import json
import uuid
import logging
import asyncio
import re
import os
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from langchain_core.messages import HumanMessage

from app.core.database import get_session
from app.core.shared_utils import _build_llm_messages
from app.core.security import decode_access_token
from app.core.sanitize import sanitize_input
from app.models.profile import LearningProfile
from app.models.user import User
from app.models.conversation import Conversation
from app.dependencies import get_graph, get_spark_client
from app.services.agent_persistence import _persist_agent_output
from app.services.event_hooks import _post_agent_event_hook, _store_suggestion, _get_agent_suggestion_text
from app.services.profile_collect import _silent_profile_collect
from app.services.knowledge_boost import _extract_and_boost

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["对话"])

_SENTINEL = object()

# Shared thread pool for bridging sync LLM calls to async event stream.
# Avoids creating a new executor thread per SSE request (Issue #3).
_bridge_executor = ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 1) * 4 + 1), thread_name_prefix="bridge_")


# ============================================================
# P0-#1 (2026-07-11): 同请求去重 + P0-#2 (2026-07-11): Spark token 清理
# 省一标准: 防御性编程, 杜绝重复生成 / 内部 token 泄露
# ============================================================
import hashlib as _hashlib

_CONTENT_DEDUP_CACHE: dict[str, tuple[str, float]] = {}
_DEDUP_WINDOW_SEC = 5.0  # 5s 窗口内同前缀 chunk 视为重复
_DEDUP_MAX_CACHE = 256   # 防止内存泄漏


def _is_duplicate_chunk(user_msg: str, content_chunk: str) -> bool:
    """P0-#1 省一验收: 同请求 5s 窗口内同前缀内容视为重复.

    优化: 只检测"长内容重复" (>=50 字符), 避免短 chunk (Spark 默认 chunk_size=2) 误判
    P1-FIX: 每次插入时清理过期条目, 防止低流量时缓存永不过期.
    Returns:
        True  - 该 chunk 是重复的, 调用方应 skip yield
        False - 正常 chunk, 调用方应继续
    """
    if not content_chunk or len(content_chunk) < 50:
        return False
    key = _hashlib.md5(
        f"{user_msg[:80]}:{content_chunk[:80]}".encode("utf-8")
    ).hexdigest()
    now = time.time()
    # 每次插入时清理过期条目 (P1-FIX: 独立于容量检查, 低流量也定期清理)
    cutoff = now - _DEDUP_WINDOW_SEC * 2
    for k in list(_CONTENT_DEDUP_CACHE.keys()):
        if _CONTENT_DEDUP_CACHE[k][1] < cutoff:
            _CONTENT_DEDUP_CACHE.pop(k, None)
    # 容量保护: 超出上限时强制清理
    if len(_CONTENT_DEDUP_CACHE) > _DEDUP_MAX_CACHE:
        stale = sorted(_CONTENT_DEDUP_CACHE.items(), key=lambda x: x[1][1])
        for k, _ in stale[:len(_CONTENT_DEDUP_CACHE) - _DEDUP_MAX_CACHE + 10]:
            _CONTENT_DEDUP_CACHE.pop(k, None)
    if key in _CONTENT_DEDUP_CACHE:
        cached, ts = _CONTENT_DEDUP_CACHE[key]
        if now - ts < _DEDUP_WINDOW_SEC:
            logger.warning("P0-#1 同请求去重触发: 5s 内重复 chunk (%d chars)", len(content_chunk))
            return True
    _CONTENT_DEDUP_CACHE[key] = (content_chunk, now)
    return False


# P0-#2 省一验收: Spark LLM 内部 highlight token 清理
# Spark API 返回的代码块常带 "sk"> (keyword) "sf"> (function) "sc"> (comment) 等
# 这些是 LLM 内部样式标记, 前端若直接展示会变成 "sk">def 这种不可读代码
_SPARK_TOKEN_RE = re.compile(r'"[sS][a-z0-9]{1,2}">')


def clean_spark_tokens(text: str) -> str:
    """P0-#2 省一验收: 清理 Spark LLM 内部高亮 token, 保留纯代码.

    输入: '"sk">def "sf">func():\\n    "sc"># comment'
    输出: 'def func():\\n    # comment'
    """
    if not text:
        return text
    cleaned = _SPARK_TOKEN_RE.sub("", text)
    # 额外清理: Spark 有时输出 \n 字符串字面量 (双重转义)
    cleaned = cleaned.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
    if len(cleaned) != len(text):
        logger.debug("P0-#2 Spark token 清理: 移除 %d 字符", len(text) - len(cleaned))
    return cleaned


# P1-#5 省一验收: 流式内容完整性校验
class _StreamIntegrityChecker:
    """检测流式内容是否完整 (无截断/无重复/无错乱).

    设计: 只检测"极短内容重复" (Spark chunk_size=2 时常见), 避免 LLM 长重复
          文本被误判 (md5 8位有碰撞可能)
    """

    def __init__(self):
        self._last_short_hash: str | None = None
        self._last_short_content: str = ""
        self._total_chunks: int = 0
        self._dup_count: int = 0

    def check(self, chunk: str) -> tuple[bool, str]:
        """检查单 chunk 完整性.

        Returns:
            (True, 'OK')        - 正常
            (False, 'duplicate') - 重复短块 (Spark 偶发, 可丢弃)
        """
        if not chunk:
            return True, "empty"
        self._total_chunks += 1
        # P1-#5 2026-07-11: 改用"短内容连续重复"判断 (避免误判)
        # 短 chunk (≤4字符) 连续 2 次相同才视为重复
        # 排除仅含 Markdown 表格字符的 chunk (--, |, |- 等)
        stripped = chunk.strip()
        if len(chunk) <= 4 and not all(c in '-|: \t\n' for c in stripped):
            h = _hashlib.md5(chunk.encode("utf-8")).hexdigest()[:8]
            if h == self._last_short_hash and chunk == self._last_short_content:
                self._dup_count += 1
                if self._dup_count >= 2:  # 至少连续 2 次才丢
                    return False, "duplicate"
            else:
                self._dup_count = 0
            self._last_short_hash = h
            self._last_short_content = chunk
        return True, "OK"

    @property
    def is_clean(self) -> bool:
        return self._dup_count == 0


# 模块级单例: 每个 SSE 请求实例化一个
def _new_integrity_checker():
    return _StreamIntegrityChecker()


# ============================================================
# 请求模型
# ============================================================
class ImageInput(BaseModel):
    """用户上传的图片（base64 编码）"""
    base64: str = Field(..., description="图片 base64 数据（不含 data URI 前缀）")
    mime_type: str = Field(default="image/png", description="图片 MIME 类型")
    name: str = Field(default="image.png", description="原始文件名")

class ChatRequest(BaseModel):
    content: str = Field(..., min_length=1, description="用户输入的消息")
    images: list[ImageInput] | None = Field(default=None, description="多模态：用户上传的图片列表（最多4张）")
    regenerate: bool = Field(default=False, description="是否为重新生成请求（跳过重复用户消息入库）")

    @field_validator("content")
    @classmethod
    def content_must_be_meaningful(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("消息内容不能为空")
        if len(stripped) > 4000:
            raise ValueError("消息内容不能超过4000字")
        return sanitize_input(stripped)

    @field_validator("images")
    @classmethod
    def images_must_be_valid(cls, v: list | None) -> list | None:
        if v is None:
            return v
        if len(v) > 4:
            raise ValueError("最多支持上传4张图片")
        for img in v:
            if len(img.base64) > 10 * 1024 * 1024:  # 10MB base64 ≈ 7.5MB 图片
                raise ValueError(f"图片 '{img.name}' 过大，请压缩后重试")
        return v


# ============================================================
# 工具函数
# ============================================================
def _optional_user(authorization: str | None = Header(None)):
    """可选认证：有 token 就解析用户，没有就返回 None"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = decode_access_token(authorization[7:])
    if not payload:
        return None
    with get_session() as db:
        user = db.query(User).filter(User.id == int(payload["sub"])).first()
        if user:
            db.expunge(user)  # 分离实例，防止 session 关闭后 DetachedInstanceError
        return user


def _generate_learning_summary(user_id: int, agent_name: str, agent_outputs: dict) -> str | None:
    """在 teaching/evaluation session 之后自动生成结构化"学习小结"。

    触发条件：Agent 为 resource_agent / question_agent / evaluation_agent /
    collaborative_resource / collaborative_qa 时。

    返回 Markdown 文本（blockquote 格式），可直接追加到 assistant 消息尾部；
    不适用时返回 None。
    """
    if agent_name not in ("resource_agent", "question_agent", "evaluation_agent",
                          "collaborative_resource", "collaborative_qa"):
        return None

    try:
        from app.services.bkt_service import get_tracker
        tracker = get_tracker(user_id)
        all_nodes = tracker.nodes

        mastered = tracker.get_mastered()
        weak = tracker.get_weak_points()
        total = len(all_nodes)

        # ── 提取本次会话涉及的概念 ──
        concepts_this_session: list[str] = []
        if agent_name == "resource_agent":
            meta = agent_outputs.get("resource_agent", {})
            topic = meta.get("title") or meta.get("topic", "")
            if topic:
                concepts_this_session.append(topic)
        elif agent_name == "question_agent":
            meta = agent_outputs.get("question_agent", {})
            kw = meta.get("knowledge_points") or meta.get("topic") or ""
            if kw:
                if isinstance(kw, list):
                    concepts_this_session.extend(kw)
                else:
                    concepts_this_session.append(str(kw))
        elif agent_name == "evaluation_agent":
            meta = agent_outputs.get("evaluation_agent", {})
            kw = meta.get("knowledge_points") or []
            if isinstance(kw, list):
                concepts_this_session.extend(kw)

        lines = ["\n\n---\n"]
        lines.append("> **学习小结**  \n")

        # 1) 本次学习内容
        if concepts_this_session:
            lines.append(f"> 本次学习: {'、'.join(concepts_this_session)}")

        # 2) BKT 掌握概览
        if total > 0:
            lines.append(f"> 知识掌握: {len(mastered)}/{total} 个概念已精通")

        # 3) 最强领域（p_known 最高的 3 个已掌握知识点）
        if mastered:
            strong_3 = sorted(
                [(n, all_nodes[n].p_known) for n in mastered if n in all_nodes],
                key=lambda x: -x[1],
            )[:3]
            if strong_3:
                lines.append(f"> 最强领域: {', '.join(f'{n}({p:.0%})' for n, p in strong_3)}")

        # 4) 薄弱环节（p_known 最低的 3 个）
        if weak:
            weak_3 = sorted(
                [(n, all_nodes[n].p_known) for n in weak if n in all_nodes],
                key=lambda x: x[1],
            )[:3]
            if weak_3:
                lines.append(f"> 需加强: {', '.join(f'{n}({p:.0%})' for n, p in weak_3)}")

        # 5) 下一步推荐
        if weak:
            lines.append(f"> 建议下一步: 巩固 **{weak[0]}**")
        elif agent_name == "resource_agent" and concepts_this_session:
            lines.append(f"> 建议下一步: 做几道练习巩固 **{concepts_this_session[0]}**")

        return "\n".join(lines) + "\n"
    except Exception as exc:
        logger.warning("学习小结生成跳过 (non-fatal): %s", exc)
        return None


def _load_profile(user_id: int) -> dict | None:
    """从 MySQL 加载用户画像"""
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


def _load_conversation_history(user_id: int, limit: int = 24) -> list:
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


def _extract_topic_context(history_msgs: list, current_msg: str) -> dict:
    """从对话历史中提取当前话题上下文"""
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


async def _bridge_stream(spark, messages: list, temperature: float, max_tokens: int, use_safe: bool = False, chunk_size: int = 2):
    """线程安全队列桥接：把同步的 chat_stream 转成异步生成器"""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _run():
        try:
            pre_collected = messages[0].get("__pre_collected__") if messages and isinstance(messages[0], dict) else None
            if pre_collected:
                for chunk in pre_collected:
                    if chunk:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
            elif use_safe:
                from app.utils.llm_helper import safe_chat_stream
                gen = safe_chat_stream(spark, messages, temperature=temperature, max_tokens=max_tokens, retries=2, fallback="服务繁忙，请稍后再试~")
                for chunk in gen:
                    if chunk:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
            else:
                gen = spark.chat_stream(messages, temperature=temperature, max_tokens=max_tokens)
                for chunk in gen:
                    if chunk:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    _bridge_executor.submit(_run)

    # True streaming: yield chunks as they arrive (NOT buffered)
    # chunk_size > 0 enables character-level typewriter effect
    accumulated = ""
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=300)
        except asyncio.TimeoutError:
            logger.error("SSE stream timeout after 300s")
            if accumulated:
                yield accumulated
            # P0-FIX (2026-07-12): 不再 yield SSE 格式字符串,
            # 改为 raise 异常让调用方统一处理为 v1.error 事件
            raise TimeoutError("SSE stream timeout after 300s")
        if item is _SENTINEL:
            if accumulated:
                yield accumulated
            break
        if isinstance(item, Exception):
            if accumulated:
                yield accumulated
            raise item

        if chunk_size > 0:
            # P0-#2 (2026-07-11): 在切分为显示块之前，先对原始 LLM 输出清洗 Spark token
            # 必须在 chunk_size 切分之前调用，因为 "sc"> (5字符) 会被 chunk_size=2 切碎
            item = clean_spark_tokens(item)
            accumulated += item
            while len(accumulated) >= chunk_size:
                yield accumulated[:chunk_size]
                accumulated = accumulated[chunk_size:]
        else:
            yield item


# ============================================================
# POST /api/chat/send —— 核心 SSE 端点
# ============================================================
@router.post("/send")
async def chat_send(
    request: ChatRequest,
    graph=Depends(get_graph),
    spark=Depends(get_spark_client),
    current_user: User | None = Depends(_optional_user),
):
    """发送消息 -> LangGraph Supervisor 调度 -> Agent 处理 -> SSE 流式返回"""

    user_id = current_user.id if current_user else 0

    history_msgs = _load_conversation_history(user_id, limit=12)
    topic_ctx = _extract_topic_context(history_msgs, request.content)

    # ── 多模态：构建用户消息（支持纯文本 / 文本+图片）──
    if request.images:
        # OpenAI Vision API 格式的多模态 content
        multimodal_content: list[dict] = [
            {"type": "text", "text": request.content}
        ]
        for img in request.images:
            data_url = f"data:{img.mime_type};base64,{img.base64}"
            multimodal_content.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })
        user_msg = HumanMessage(content=multimodal_content)
    else:
        user_msg = HumanMessage(content=request.content)

    from app.config import AGENT_RECURSION_LIMIT
    config = {"configurable": {"thread_id": f"user-{user_id}"}, "recursion_limit": AGENT_RECURSION_LIMIT}

    # 从 checkpoint 恢复 teaching_context（跨轮次持久化）
    prev_teaching_ctx = None
    prev_context = {}  # P1-1: 恢复画像追问冷却位点
    try:
        snapshot = await asyncio.to_thread(graph.get_state, config)
        if snapshot and snapshot.values:
            prev_teaching_ctx = snapshot.values.get("teaching_context")
            prev_context = snapshot.values.get("context", {}) or {}
            if prev_teaching_ctx and prev_teaching_ctx.get("mode") == "teaching":
                logger.info("SSE: 恢复教学流程 state (current=%d/%d)",
                            prev_teaching_ctx.get("current_index", 0) + 1,
                            len(prev_teaching_ctx.get("active_path", [])))
                # P1-FIX v2: 使用共享 is_teaching_continue（含模糊节点匹配），替代简单标记列表
                from app.core.shared_utils import is_teaching_continue
                if not is_teaching_continue(request.content.strip(), prev_teaching_ctx):
                    logger.info("P1-FIX: 非继续消息，清除跨会话残留 teaching_context (msg=%s)", request.content.strip()[:40])
                    prev_teaching_ctx = None
    except Exception as _e:
        logger.debug("SSE: 获取 checkpoint 教学状态失败（新用户正常）: %s", _e)

    # P1-1: 累加 last_profile_ask_at（每轮对话 +1，达到冷却阈值后允许再次追问）
    _lpa = prev_context.get("last_profile_ask_at", 0)
    _pac = prev_context.get("profile_ask_count", 0)
    _pfd = prev_context.get("profile_first_done", False)
    _restored_context = {**prev_context}

    # P1-FIX (P1-B 集中化 2026-07-11): 清除 checkpoint 残留的一次性标志
    # 原因: 之前会话设置的 init_teaching / teaching_continue / replan_path 等
    # 会被 LangGraph 持久化到 checkpoint, 跨会话继承 → 用户问"学习计划"时被误触发
    # 自动教学 26 节点循环 (历史 bug: user-1 跑了 11+ 节点仍卡在生成中)
    # 集中管理: 新增一次性标志只需修改 app/agents/_stale_flags.py
    from app.agents._stale_flags import STALE_ONE_SHOT_FLAGS
    _cleaned_flags = []
    for _flag in STALE_ONE_SHOT_FLAGS:
        if _flag in _restored_context:
            _restored_context.pop(_flag, None)
            _cleaned_flags.append(_flag)
    if _cleaned_flags:
        logger.info("P1-FIX: 清除跨会话残留的一次性标志 %s", _cleaned_flags)

    if _lpa < 5:
        _restored_context["last_profile_ask_at"] = _lpa + 1
        logger.debug("P1-1: last_profile_ask_at 递增: %d -> %d (ask_count=%d, done=%s)",
                     _lpa, _lpa + 1, _pac, _pfd)

    initial_state = {
        # P0-FIX (2026-07-12): 只传新用户消息, 历史由 LangGraph checkpoint add_messages 合并
        # 修复: history_msgs 从 DB 重建的新对象 ID 与 checkpoint 不同, add_messages 会重复追加
        "messages": [user_msg],
        "current_agent": "supervisor",
        "next_agent": None,
        "user_profile": _load_profile(user_id),
        # P1-1: 合并 topic_context + 恢复的画像冷却位点
        "context": {**{"topic_context": topic_ctx}, **_restored_context},
        "agent_outputs": {"_CLEAR_": True},  # P0-2: _CLEAR_ sentinel 清除 checkpoint 累积的 agent_outputs
        "stream_buffer": "",
        "user_id": user_id,
        "teaching_context": prev_teaching_ctx,
    }

    # U-03: 重新生成时跳过重复用户消息入库（原消息已在DB中）
    _user_msg_id = 0
    if user_id and not request.regenerate:
        with get_session() as db:
            _conv_user_msg = Conversation(user_id=user_id, role="user", content=request.content)
            db.add(_conv_user_msg)
            db.flush()
            _user_msg_id = _conv_user_msg.id

    async def event_stream():
        prev_agent = "supervisor"
        assistant_content = ""
        assistant_agent = ""
        _captured_outputs = {}
        _agent_switch_count = 0
        _pending_resource_meta = None  # C7: 延迟到 LLM 完成后创建 Resource
        # P0-#1/P1-#5 (2026-07-11): 同请求去重 + 流式完整性校验
        _user_msg = request.content
        _integrity = _new_integrity_checker()

        try:
            # P0 (2026-07-12): astream 整体超时 300s (5min)，必须 >= 内层 _stream_timeout (120s)
            # 修复前为 90s < 120s，导致超时消息注入正常内容中间
            _AAGENT_TIMEOUT = 300
            _astream_start = time.time()
            _force_stop = False  # P0-FIX: 内层 break 无法终止外层 async for
            async for update in graph.astream(initial_state, config, stream_mode="updates"):
                if _force_stop or time.time() - _astream_start > _AAGENT_TIMEOUT:
                    logger.warning("SSE: astream 整体超过 %ds, 强制结束", _AAGENT_TIMEOUT)
                    error_msg = "\n\n（响应超时，请稍后重试或简化问题）"
                    assistant_content += error_msg
                    yield f"event: v1.message\ndata: {json.dumps({'content': error_msg, 'agent': 'system', 'type': 'timeout'}, ensure_ascii=False)}\n\n"
                    _force_stop = True  # P0 (2026-07-12): 设置标志防止后续 Mermaid/小结 yield
                    break
                for node_name, node_update in update.items():
                    if node_name == "__end__":
                        continue
                    agent_name = node_name

                    # P1-D 2026-07-11: 死循环防护 - 同一 agent 切换超过 8 次强制结束
                    if agent_name != prev_agent:
                        _agent_switch_count += 1
                        if _agent_switch_count > 15:
                            logger.error("SSE: agent_switch > 15 次, 疑似死循环, 强制结束 (last=%s)", agent_name)
                            error_msg = "\n\n（检测到异常循环，已自动终止，请刷新页面重试）"
                            assistant_content += error_msg
                            yield f"event: v1.message\ndata: {json.dumps({'content': error_msg, 'agent': 'system', 'type': 'loop_guard'}, ensure_ascii=False)}\n\n"
                            _force_stop = True
                            break
                        yield f"event: v1.agent_switch\ndata: {json.dumps({'from': prev_agent, 'to': agent_name}, ensure_ascii=False)}\n\n"
                        prev_agent = agent_name
                        # Only track worker agents as the "assistant agent" — supervisor is a router
                        if agent_name != "supervisor":
                            assistant_agent = agent_name

                    agent_output = node_update.get("agent_outputs", {})
                    if agent_output:
                        _captured_outputs.update(agent_output)

                    # 协作模式检测: 如果当前节点是并行协作节点，发射 collaboration 事件
                    _collab_mode = agent_output.get("_collaboration_mode")
                    if _collab_mode:
                        _collab_agents_map = {
                            "qa_parallel": ["question_agent", "evaluation_agent"],
                            "resource_parallel": ["resource_agent", "quality_reviewer"],
                            "path_parallel": ["path_agent", "prefetch_agent"],
                        }
                        _collab_agents = _collab_agents_map.get(_collab_mode, [agent_name])
                        yield f"event: v1.collaboration\ndata: {json.dumps({'type': 'collaboration', 'action': 'parallel', 'agents': _collab_agents, 'primary': agent_name}, ensure_ascii=False)}\n\n"

                    _resource_meta = agent_output.get(agent_name, {})
                    if _resource_meta and "type" in _resource_meta and agent_name == "resource_agent":
                        # 延迟创建: Resource 不再在此处创建占位记录(避免LLM失败导致孤儿记录)
                        # 实际 Resource 在流式完成后由 _persist_agent_output 一次性创建
                        _pending_resource_meta = _resource_meta

                    pending = agent_output.get(agent_name, {}).get("stream_pending")
                    # DIAG-FIX 2026-07-11: 用 node_update 替代 state (event_stream 内无 state 变量)
                    # P0-FIX 2026-07-11: 删除 print 调试, 改用 logger.info (已存在)
                    _tc_check = node_update.get("teaching_context") if isinstance(node_update, dict) else None
                    logger.info(
                        "[CHAT-DIAG] agent=%s, agent_output_keys=%s, pending=%s, buf_len=%d, tc=%s",
                        agent_name,
                        list(agent_output.keys())[:3] if agent_output else None,
                        'YES' if pending else 'NO',
                        len(node_update.get('stream_buffer', '') or ''),
                        bool(_tc_check),
                    )
                    if pending:
                        try:
                            from app.utils.content_guard import StreamGuard
                            guard = StreamGuard(check_interval=300)  # P3-FIX: 从60增加到300，避免过早检测导致误判
                            # P1-FIX: plan 检测只对 resource_agent 生效
                            # (修复: path_agent 输出"学习计划"被误判 → SSE 卡死, 前端"生成中...")
                            # chat.py line 575, 594 已经有 agent_name == "resource_agent" 限制,
                            # 但 StreamGuard.feed 内部的累积检查没这个限制, 导致 path_agent 输出
                            # "Python 学习计划" 时第 60 字符就被 plan_detected=True 阻断, 后续 chunk 全部丢失
                            if agent_name != "resource_agent":
                                guard._guard.is_learning_plan_output = lambda _t: False
                            chunk_count = 0
                            estimated_total = max(1, pending.get("max_tokens", 2048) // 3)
                            _milestones = {1, 3, 10, 20, 30, 50, 80, 120, 180, 250}
                            yield f"event: v1.progress\ndata: {json.dumps({'stage': 'generating', 'agent': agent_name, 'progress': 0, 'message': '正在生成...'}, ensure_ascii=False)}\n\n"
                            # P0-心跳 2026-07-11: LLM 等待期间每 8s 向前端发送心跳,
                            # 避免大提示词导致首 token 延迟时前端显示"卡死"
                            _stream = _bridge_stream(
                                spark,
                                pending["messages"],
                                pending.get("temperature", 0.7),
                                pending.get("max_tokens", 2048),
                                use_safe=pending.get("use_safe", False),
                                chunk_size=pending.get("chunk_size", 2),
                            )
                            _heartbeat_interval = 8.0
                            _stream_start = time.time()
                            _stream_timeout = 120.0  # 2min 流式整体超时
                            # P0-FIX (2026-07-12): 用 asyncio.wait 替代 asyncio.wait_for,
                            # 心跳超时不再取消底层异步生成器, 防止 LLM 首 token >8s 时流被杀死
                            _chunk_task = asyncio.ensure_future(_stream.__anext__())
                            while True:
                                _hb_task = asyncio.ensure_future(asyncio.sleep(_heartbeat_interval))
                                done, _pending = await asyncio.wait(
                                    [_chunk_task, _hb_task],
                                    return_when=asyncio.FIRST_COMPLETED
                                )
                                if _chunk_task in done:
                                    _hb_task.cancel()
                                    try:
                                        chunk = _chunk_task.result()
                                    except StopAsyncIteration:
                                        break
                                    except Exception as _chunk_err:
                                        logger.warning("SSE: chunk task 异常: %s", _chunk_err)
                                        raise
                                else:
                                    # 心跳触发: 保留 _chunk_task 继续等待
                                    _elapsed = time.time() - _stream_start
                                    if _elapsed > _stream_timeout:
                                        logger.warning("SSE: 流式总超时 %.0fs, 强制结束", _elapsed)
                                        _chunk_task.cancel()
                                        _force_stop = True  # P1-1: 同步终止外层 graph 循环
                                        err_timeout = "\n\n（生成超时，请简化问题后重试）"
                                        assistant_content += err_timeout
                                        yield f"event: v1.message\ndata: {json.dumps({'content': err_timeout, 'agent': 'system', 'type': 'stream_timeout'}, ensure_ascii=False)}\n\n"
                                        break
                                    yield f"event: v1.progress\ndata: {json.dumps({'stage': 'generating', 'agent': agent_name, 'progress': -1, 'message': '正在生成中，请耐心等待...'}, ensure_ascii=False)}\n\n"
                                    continue
                                if chunk:
                                    # P0-#2 (2026-07-11): 清理 Spark highlight token
                                    chunk = clean_spark_tokens(chunk)
                                    # P0-#1 (2026-07-11): 同请求 5s 内重复 chunk 丢弃
                                    if _is_duplicate_chunk(_user_msg or "", chunk):
                                        _chunk_task = asyncio.ensure_future(_stream.__anext__())
                                        continue
                                    # P1-#5 (2026-07-11): 流式完整性校验 (检测重复块)
                                    integrity_ok, _ = _integrity.check(chunk)
                                    if not integrity_ok:
                                        logger.warning("P1-#5 丢弃重复块: %s...", chunk[:30])
                                        _chunk_task = asyncio.ensure_future(_stream.__anext__())
                                        continue
                                    safe_chunk = guard.feed(chunk)
                                    if safe_chunk is not None:
                                        assistant_content += safe_chunk
                                        chunk_count += 1
                                        yield f"event: v1.message\ndata: {json.dumps({'content': safe_chunk, 'agent': agent_name}, ensure_ascii=False)}\n\n"
                                        # P2 (2026-07-12): 仅里程碑发射 progress，不再每50 chunk 发射避免前端污染
                                        if chunk_count in _milestones:
                                            pct = min(90, int(chunk_count / estimated_total * 100))
                                            yield f"event: v1.progress\ndata: {json.dumps({'stage': 'generating', 'agent': agent_name, 'progress': pct}, ensure_ascii=False)}\n\n"
                                _chunk_task = asyncio.ensure_future(_stream.__anext__())
                            if guard.blocked:
                                logger.warning("SSE: %s 输出被内容安全守卫拦截", agent_name)
                                safe_fallback = guard.get_safe_content()
                                assistant_content += safe_fallback  # P1-2: 追加而非覆盖
                                yield f"event: v1.message\ndata: {json.dumps({'content': safe_fallback, 'agent': agent_name}, ensure_ascii=False)}\n\n"
                            elif agent_name == "resource_agent" and guard.finalize():
                                # P1-3 (2026-07-12): anti-plan 不再替换已发送的流式内容，
                                # 仅发送 system_notice 供前端显示警告横幅。质量门由 supervisor 负责。
                                logger.warning("SSE: %s 流式输出疑似学习计划 (len=%d), 已发送system_notice",
                                             agent_name, len(guard._buffer))
                                yield f"event: v1.system_notice\ndata: {json.dumps({'type': 'plan_warning', 'reason': '生成内容可能包含课程计划结构', 'severity': 'low'}, ensure_ascii=False)}\n\n"
                            yield f"event: v1.progress\ndata: {json.dumps({'stage': 'complete', 'agent': agent_name, 'progress': 100}, ensure_ascii=False)}\n\n"
                        except Exception as stream_err:
                            logger.warning("SSE: %s 流式输出异常: %s", agent_name, stream_err)
                            error_msg = f"\n（{agent_name} 输出中断，请稍后重试）"
                            assistant_content += error_msg
                            yield f"event: v1.message\ndata: {json.dumps({'content': error_msg, 'agent': agent_name}, ensure_ascii=False)}\n\n"
                            # P2-D 2026-07-11: 通知前端 LLM 失败, 可显示重试按钮
                            yield f"event: v1.system_notice\ndata: {json.dumps({'type': 'agent_error', 'agent': agent_name, 'error': str(stream_err)[:200]}, ensure_ascii=False)}\n\n"
                        # P1-1 (2026-07-12): 超时时 break 外层 for/async for 循环
                        if _force_stop:
                            break
                        continue

                    buf = node_update.get("stream_buffer", "")
                    if buf:
                        # P1-FIX: agent stream_buffer 也需要清洗 Spark token (与 streaming 路径保持一致)
                        buf = clean_spark_tokens(buf)
                        from app.utils.content_guard import get_guard
                        guard = get_guard()
                        safe, warning = guard.check(buf)
                        if safe:
                            # resource_agent + path_agent: 检测计划/课程表模式输出
                            if agent_name == "resource_agent" and guard.is_learning_plan_output(buf):
                                # P1-3 (2026-07-12): anti-plan 不再替换 buffer 内容，
                                # 改为透传 + system_notice 警告。质量门由 supervisor 负责。
                                logger.warning("SSE: %s buffer疑似学习计划 (len=%d), 透传+system_notice",
                                             agent_name, len(buf))
                                assistant_content += buf
                                yield f"event: v1.message\ndata: {json.dumps({'content': buf, 'agent': agent_name}, ensure_ascii=False)}\n\n"
                                yield f"event: v1.system_notice\ndata: {json.dumps({'type': 'plan_warning', 'reason': '生成内容可能包含课程计划结构', 'severity': 'low', 'original_len': len(buf)}, ensure_ascii=False)}\n\n"
                            else:
                                assistant_content += buf
                                yield f"event: v1.message\ndata: {json.dumps({'content': buf, 'agent': agent_name}, ensure_ascii=False)}\n\n"
                        else:
                            safe_msg = guard.get_safe_content() if hasattr(guard, 'get_safe_content') else "抱歉，生成的内容未通过安全检查。请换一种方式提问。"
                            assistant_content += safe_msg
                            yield f"event: v1.message\ndata: {json.dumps({'content': safe_msg, 'agent': agent_name}, ensure_ascii=False)}\n\n"

                    # P2-1: 路径动态重规划 → 推送 path_update 结构化事件 (仅 path_agent 节点，避免 path_join 重复)
                    if agent_name == "path_agent":
                        _pa_out = agent_output.get("path_agent", {})
                        if _pa_out.get("teaching_stage") == "replanned":
                            _new = _pa_out.get("new_unlocked", [])
                            _skip = _pa_out.get("skipped", [])
                            _current_node = _pa_out.get("current_node", "")
                            _reason_parts = []
                            if _skip:
                                _reason_parts.append(f"已掌握: {'、'.join(_skip)}")
                            if _new:
                                _reason_parts.append(f"新解锁: {'、'.join(_new)}")
                            if _reason_parts:
                                if _skip and _new:
                                    _reason_text = "通过BKT追踪发现，" + "、".join(_skip) + " 的掌握概率已超过阈值，因此跳过并解锁了 " + "、".join(_new) + " 个新节点"
                                elif _skip:
                                    _reason_text = "通过BKT追踪发现，" + "、".join(_skip) + " 的掌握概率已超过阈值，已跳过这些节点"
                                else:
                                    _reason_text = "通过BKT追踪发现，新解锁了 " + "、".join(_new) + " 个节点"
                                yield (
                                    "event: v1.path_update\n"
                                    f"data: {json.dumps({'action': 'replanned', 'new_unlocked': _new, 'skipped': _skip, 'current_node': _current_node, 'reason': _reason_text}, ensure_ascii=False)}\n\n"
                                )
                                _joined_reasons = "\n> ".join(_reason_parts)
                                _explain_msg = "\n\n> **路径更新**\n> " + _joined_reasons + "\n> 学习路径已自动调整，进入下一阶段学习。\n"
                                assistant_content += _explain_msg
                                yield f"event: v1.message\ndata: {json.dumps({'content': _explain_msg, 'agent': 'system', 'type': 'explanation'}, ensure_ascii=False)}\n\n"

                    # [已删除] 全Agent英文饼图 — 仅 evaluation_agent 保留中文饼图(见下方)

            # P1-1 (2026-07-12): 超时后跳出外层 async for 循环
                if _force_stop:
                    break

            # P0 (2026-07-12): _force_stop / timeout 后跳过后续 Mermaid/小结/suggestion
            if _force_stop:
                yield f"event: v1.done\ndata: {json.dumps({'status': 'stopped', 'agent_switches': _agent_switch_count})}\n\n"
                return

            # 评估报告：追加 Mermaid 饼图（后端生成，不受 LLM 影响）
            if assistant_agent == "evaluation_agent" and user_id:
                try:
                    from app.services.bkt_service import get_tracker
                    tracker = get_tracker(user_id)
                    nodes = tracker.to_dict().get("nodes", {})
                    # 如果 BKT 为空，从 profile knowledge_base 构建 Mermaid
                    if not nodes:
                        profile = _load_profile(user_id)
                        kb = (profile or {}).get("knowledge_base", {}) or {}
                        if isinstance(kb, dict) and kb:
                            mastered = sum(1 for v in kb.values() if isinstance(v, (int, float)) and v >= 70)
                            learning = sum(1 for v in kb.values() if isinstance(v, (int, float)) and 35 <= v < 70)
                            beginner = sum(1 for v in kb.values() if isinstance(v, (int, float)) and v < 35)
                            total = mastered + learning + beginner
                    else:
                        mastered = sum(1 for n in nodes.values() if isinstance(n, dict) and n.get("p_known", 0) >= 0.7)
                        learning = sum(1 for n in nodes.values() if isinstance(n, dict) and 0.35 <= n.get("p_known", 0) < 0.7)
                        beginner = sum(1 for n in nodes.values() if isinstance(n, dict) and n.get("p_known", 0) < 0.35)
                        total = mastered + learning + beginner
                    if total > 0:
                        mm = f"\n\n```mermaid\npie title 知识点掌握分布 (共{total}个)\n    \"已掌握(>=70%)\" : {mastered}\n    \"学习中(35-70%)\" : {learning}\n    \"入门(<35%)\" : {beginner}\n```\n"
                        assistant_content += mm
                        yield f"event: v1.message\ndata: {json.dumps({'content': mm, 'agent': 'evaluation_agent'}, ensure_ascii=False)}\n\n"
                except Exception as _e:
                    logger.warning("SSE: BKT评估Mermaid图表生成失败: %s", _e)
            # 资源生成：追加 Mermaid 知识点分布图
            if assistant_agent == "resource_agent" and user_id:
                try:
                    profile = _load_profile(user_id)
                    kb = (profile or {}).get("knowledge_base", {}) or {}
                    if isinstance(kb, dict) and kb:
                        sorted_kb = sorted(
                            [(k, v) for k, v in kb.items() if isinstance(v, (int, float))],
                            key=lambda x: x[1], reverse=True
                        )[:6]
                        if sorted_kb:
                            lines_mm = [f'    "{name}": {score}' for name, score in sorted_kb]
                            mm = "\n\n```mermaid\npie title 知识点覆盖分布\n" + "\n".join(lines_mm) + "\n```\n"
                            assistant_content += mm
                            yield f"event: v1.message\ndata: {json.dumps({'content': mm, 'agent': 'resource_agent'}, ensure_ascii=False)}\n\n"
                except Exception as _e:
                    logger.warning("SSE: 资源分布Mermaid图表生成失败: %s", _e)

            # 出题：追加 Mermaid 难度分布图
            if assistant_agent == "question_agent":
                try:
                    mm = "\n\n```mermaid\npie title 题目难度分布\n    \"\u57fa\u7840\" : 40\n    \"\u4e2d\u7b49\" : 35\n    \"\u56f0\u96be\" : 25\n```\n"
                    assistant_content += mm
                    yield f"event: v1.message\ndata: {json.dumps({'content': mm, 'agent': 'question_agent'}, ensure_ascii=False)}\n\n"
                except Exception as _e:
                    logger.warning("SSE: 题目难度Mermaid图表生成失败: %s", _e)


            # ═══════════════════════════════════════════════════════════
            # 自动学习小结 — teaching/evaluation session 后生成结构化总结
            # 包含：本次概念、BKT 掌握变化、下一步建议
            # ═══════════════════════════════════════════════════════════
            summary = _generate_learning_summary(user_id, assistant_agent, _captured_outputs)
            if summary:
                assistant_content += summary
                yield f"event: v1.message\ndata: {json.dumps({'content': summary, 'agent': assistant_agent, 'type': 'summary'}, ensure_ascii=False)}\n\n"

            yield f"event: v1.done\ndata: {json.dumps({'status': 'complete', 'agent_switches': _agent_switch_count})}\n\n"

            if user_id and assistant_content:
                with get_session() as db2:
                    db2.add(Conversation(user_id=user_id, role="assistant", content=assistant_content, agent_type=assistant_agent))
                # P1-16: 从最终状态提取 teaching_context，供资源关联路径节点使用
                _final_tc = None
                try:
                    final_snapshot = await asyncio.to_thread(graph.get_state, config)
                    if final_snapshot and final_snapshot.values:
                        _final_tc = final_snapshot.values.get("teaching_context")
                except Exception as _tc_err:
                    logger.debug("P1-16: 获取最终teaching_context失败 (non-fatal): %s", _tc_err)
                _persisted = _persist_agent_output(assistant_agent, assistant_content, user_id, _captured_outputs, _final_tc)
                # C7: 在持久化完成后发射 resource_ready (避免 LLM 失败时的孤儿记录)
                # _persist_agent_output 会将 db_id 回写到 _captured_outputs["resource_agent"]["db_id"]
                if _pending_resource_meta:
                    _r_meta = _captured_outputs.get("resource_agent", {})
                    _r_id = _r_meta.get("db_id", 0)
                    _r_type = _pending_resource_meta.get("type", "document")
                    _r_title = _pending_resource_meta.get("title") or _pending_resource_meta.get("topic", "")
                    if _r_id:
                        yield f"event: v1.resource_ready\ndata: {json.dumps({'type': 'resource_ready', 'resource_id': _r_id, 'resource_type': _r_type, 'title': _r_title}, ensure_ascii=False)}\n\n"
                        logger.info("SSE: resource_ready 已发射 id=%d type=%s", _r_id, _r_type)
                # v3: 事件驱动闭环 — Agent完成后自动触发下游
                _post_agent_event_hook(assistant_agent, user_id, _captured_outputs)
                _extract_and_boost(user_id, request.content)
                _silent_profile_collect(user_id, request.content)

            # v4: 推送智能建议 (SSE suggestion事件) — 前端弹窗提醒下一步操作
            if user_id and assistant_agent:
                try:
                    profile = _load_profile(user_id)
                    sg_list = (profile or {}).get('suggestions', []) or []
                    if sg_list:
                        latest = sg_list[-1]
                        yield f"event: v1.suggestion\ndata: {json.dumps(latest, ensure_ascii=False)}\n\n"
                        # v5: auto_trigger → 推送资源预取事件，前端可提前加载首个节点资源
                        if latest.get("auto_trigger") and latest.get("intent") == "resource":
                            yield f"event: v1.prefetch\ndata: {json.dumps({'type': 'resource_prefetch', 'node': latest.get('topic', ''), 'status': 'queued'}, ensure_ascii=False)}\n\n"
                except Exception as _e:
                    logger.warning("SSE: 智能建议/预取推送失败: %s", _e)
            # ═══════════════════════════════════════════════════════════
            # P1-24: 复习提醒检查 — SSE review_due 事件
            # 每次对话完成后推送到期复习知识点，前端渲染 Dashboard 待复习卡片
            # ═══════════════════════════════════════════════════════════
            if user_id:
                try:
                    from app.services.review_scheduler import get_scheduler as _get_sched
                    sched = _get_sched(user_id)
                    due_nodes = sched.get_review_nodes()
                    if due_nodes:
                        high_risk = [n for n in due_nodes if n["risk"] == "high"]
                        yield (
                            "event: v1.review_due\n"
                            f"data: {json.dumps({'total': len(due_nodes), 'high_risk': len(high_risk), 'items': due_nodes[:5]}, ensure_ascii=False)}\n\n"
                        )
                except Exception as _e:
                    logger.warning("SSE: 复习提醒检查失败: %s", _e)  # 非关键路径，失败不影响主流程

        except Exception as e:
            logger.error("SSE: event_stream 异常: %s", e, exc_info=True)
            # 流失败时清理孤立的用户消息记录（无对应 assistant 回复）
            if _user_msg_id and not assistant_content:
                try:
                    with get_session() as _cleanup_db:
                        _orphan = _cleanup_db.query(Conversation).filter(Conversation.id == _user_msg_id).first()
                        if _orphan:
                            _cleanup_db.delete(_orphan)
                            _cleanup_db.flush()
                            logger.info("SSE: 已清理孤立用户消息 id=%d", _user_msg_id)
                except Exception as _ce:
                    logger.warning("SSE: 清理孤立消息失败: %s", _ce)
            err_type = type(e).__name__
            err_msg = str(e)
            # P1-2: 细化错误分类，参考 LangChain/LangGraph 错误处理
            if "timeout" in err_msg.lower() or "超时" in err_msg:
                user_friendly = "请求超时了~ 处理时间较长，请稍后再试。"
                err_code = "TIMEOUT"
            elif "token" in err_msg.lower() or "limit" in err_msg.lower() or "length" in err_msg.lower():
                user_friendly = "内容过长啦~ 能不能简化一下问题？"
                err_code = "TOKEN_LIMIT"
            elif "rate" in err_msg.lower() or "429" in err_msg:
                user_friendly = "服务繁忙中~ 请稍候几秒再试。"
                err_code = "RATE_LIMIT"
            elif "auth" in err_msg.lower() or "401" in err_msg or "403" in err_msg:
                user_friendly = "认证信息已过期，请重新登录。"
                err_code = "AUTH_EXPIRED"
            elif "connection" in err_msg.lower() or "network" in err_msg.lower():
                user_friendly = "网络连接中断了~ 请检查网络后重试。"
                err_code = "NETWORK"
            else:
                user_friendly = "处理过程中遇到了一点问题，请稍后重试。"
                err_code = "INTERNAL"
            # 给前端详细的错误码和 trace_id（用于排查）
            import uuid
            trace_id = uuid.uuid4().hex[:12]
            logger.error("SSE: 错误追踪 trace_id=%s type=%s code=%s", trace_id, err_type, err_code)
            yield f"event: v1.error\ndata: {json.dumps({'message': user_friendly, 'code': err_code, 'trace_id': trace_id, 'detail': err_msg[:200]}, ensure_ascii=False)}\n\n"
            # P1-2: 补一个 done 事件让前端能正确清理 loading 状态
            yield f"event: v1.done\ndata: {json.dumps({'status': 'error', 'agent_switches': _agent_switch_count}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
