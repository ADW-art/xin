"""
轻量知识库：不依赖 BGE 模型，基于 jieba 分词 + BM25 做教材检索
用于 Agent 生成时注入参考资料，确保输出有据可依

层级说明：
  1. BM25Okapi（优先）— jieba 分词 + rank_bm25 精确检索
  2. 关键词匹配（降级）— 纯 Python，零外部依赖

使用方式：
  from app.services.content_store import search_content, inject_knowledge
  results = search_content("Python装饰器", top_k=3)
"""

import logging
import os
import re
from glob import glob
from typing import Optional

logger = logging.getLogger(__name__)

# ── 模块级单例 ──
_content_store: dict = {}          # {title: {title, topic, difficulty, content, source_file}}
_bm25_corpus: list[str] = []       # 分词后的文档列表（供 BM25 索引）
_bm25_model = None                  # BM25Okapi 实例
_ready: bool = False                # 就绪标志


def is_content_ready() -> bool:
    """检查内容库是否已加载并可用"""
    return _ready


def load_content_store(materials_dir: str = None) -> int:
    """加载所有 .md 教材文件，构建 BM25 索引

    无 BGE 启动阻断风险：即使 jieba/rank_bm25 未安装，
    也会降级到纯关键词匹配模式。

    Args:
        materials_dir: 教材目录路径，默认使用 knowledge_materials/

    Returns:
        已加载的文档数量
    """
    global _content_store, _bm25_corpus, _bm25_model, _ready

    if _ready:
        return len(_content_store)

    if materials_dir is None:
        materials_dir = os.path.join(
            os.path.dirname(__file__),
            "..", "scripts", "knowledge_materials"
        )
        materials_dir = os.path.abspath(materials_dir)

    if not os.path.isdir(materials_dir):
        logger.warning("ContentStore: 教材目录不存在 %s", materials_dir)
        return 0

    md_files = glob(os.path.join(materials_dir, "*.md"))
    if not md_files:
        logger.warning("ContentStore: 没有找到 .md 教材文件")
        return 0

    _content_store = {}
    _bm25_corpus = []

    for filepath in md_files:
        doc = _parse_markdown_doc(filepath)
        if doc:
            _content_store[doc["title"]] = doc
            # 为 BM25 准备分词后的文本
            try:
                import jieba
                _bm25_corpus.append(" ".join(jieba.cut(doc["content"])))
            except ImportError:
                _bm25_corpus.append(doc["content"])
            logger.debug("ContentStore: 已加载 %s", doc["title"])

    # ── 构建 BM25 索引 ──
    if _bm25_corpus:
        try:
            from rank_bm25 import BM25Okapi
            _bm25_model = BM25Okapi([corpus.split() for corpus in _bm25_corpus])
            logger.info("ContentStore: BM25 索引构建完成 (%d 篇文档)", len(_content_store))
        except ImportError:
            logger.warning(
                "ContentStore: rank_bm25 未安装，降级为关键词匹配"
                "（安装命令: pip install rank-bm25 jieba）"
            )

    _ready = True
    logger.info("ContentStore: 加载完成，共 %d 篇教材", len(_content_store))
    return len(_content_store)


def _parse_markdown_doc(filepath: str) -> Optional[dict]:
    """解析带 frontmatter 风格元数据的 .md 教材文件

    支持的元数据行格式:
      # title: 文档标题
      # topic: 标签1, 标签2, 标签3
      # difficulty: beginner|intermediate|advanced

    正文从第一个非元数据行开始。
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception as e:
        logger.warning("ContentStore: 读取失败 %s: %s", filepath, e)
        return None

    lines = raw.split("\n")
    metadata = {"title": "", "topic": "", "difficulty": "beginner"}
    content_start = 0

    # 扫描元数据行（必须在正文之前连续出现）
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# title:"):
            metadata["title"] = _extract_tag_value(stripped, "title:")
            content_start = i + 1
        elif stripped.startswith("# topic:"):
            metadata["topic"] = _extract_tag_value(stripped, "topic:")
            content_start = i + 1
        elif stripped.startswith("# difficulty:"):
            metadata["difficulty"] = _extract_tag_value(stripped, "difficulty:")
            content_start = i + 1
        elif stripped == "---":
            content_start = i + 1
            continue
        else:
            # 第一个非元数据行 → 正文开始
            if not stripped.startswith("# ") or any(
                kw in stripped for kw in ["什么是", "概述", "链表", "装饰器", "推导", "结构", "语法", "基本"]
            ):
                content_start = i
                break

    if not metadata["title"]:
        metadata["title"] = os.path.splitext(os.path.basename(filepath))[0]

    # 从 content_start 开始提取正文（跳过可能的空行）
    while content_start < len(lines) and lines[content_start].strip() == "":
        content_start += 1

    content = "\n".join(lines[content_start:]).strip()
    if not content:
        logger.warning("ContentStore: 文件 %s 无正文内容", filepath)
        return None

    return {
        "title": metadata["title"],
        "topic": metadata["topic"],
        "difficulty": metadata["difficulty"],
        "content": content,
        "source_file": os.path.basename(filepath),
    }


def _extract_tag_value(line: str, tag: str) -> str:
    """从 '# tag: value' 格式行中提取值"""
    value = line.replace(f"# {tag}", "", 1).strip()
    return value


def search_content(query: str, top_k: int = 3) -> list[dict]:
    """检索与查询最相关的教材文档

    优先使用 BM25Okapi 精确打分，不可用时降级为关键词匹配。

    Args:
        query:  查询文本
        top_k:  返回结果数量

    Returns:
        [{title, topic, difficulty, content, source_file, score}, ...]
    """
    global _content_store, _bm25_model, _ready

    if not _ready:
        load_content_store()

    if not _content_store:
        return []

    titles = list(_content_store.keys())

    # ── 路径1：BM25 精确检索 ──
    if _bm25_model is not None:
        try:
            import jieba
            tokenized = " ".join(jieba.cut(query))
            scores = _bm25_model.get_scores(tokenized.split())
            # 处理可能的 None 值
            cleaned_scores = [float(s) if s is not None else 0.0 for s in scores]
            ranked = sorted(enumerate(cleaned_scores), key=lambda x: x[1], reverse=True)
            results = []
            for idx, score in ranked[:top_k]:
                if idx < len(titles):
                    title = titles[idx]
                    results.append({**_content_store[title], "score": score})
            if results:
                logger.debug(
                    "ContentStore: BM25 检索 '%s' → %d 条结果",
                    query[:40], len(results)
                )
            return results
        except Exception as e:
            logger.warning("ContentStore: BM25 检索失败，回退关键词匹配: %s", e)

    # ── 路径2：关键词匹配降级 ──
    query_terms = set(query.lower().split())
    results = []
    for title, doc in _content_store.items():
        content_lower = doc["content"].lower()
        title_lower = title.lower()
        # 计算匹配词数
        hit_count = sum(
            1 for term in query_terms
            if term in content_lower or term in title_lower
        )
        if hit_count > 0:
            results.append({**doc, "score": float(hit_count)})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def get_content_by_topic(topic: str) -> list[dict]:
    """按主题标签查找所有匹配的教材文档

    Args:
        topic: 话题标签（如 "Python"、"数据结构"）

    Returns:
        匹配的文档列表
    """
    global _content_store, _ready

    if not _ready:
        load_content_store()

    if not _content_store:
        return []

    topic_lower = topic.lower().strip()
    results = []

    for title, doc in _content_store.items():
        # 检查 topic 标签
        doc_topics = [
            t.strip().lower()
            for t in doc.get("topic", "").split(",")
        ]
        if topic_lower in doc_topics:
            results.append(doc)
            continue
        # 标题部分匹配也算
        if topic_lower in title.lower():
            results.append(doc)

    return results


def inject_knowledge(messages: list[dict], topic: str) -> list[dict]:
    """将教材库参考资料注入到系统提示词中

    在已有的 system 消息末尾追加参考资料，确保 Agent 生成
    的内容有教材依据，避免编造概念。

    Args:
        messages: LLM 消息列表 [{role, content}, ...]
        topic:    当前学习主题

    Returns:
        注入后新的消息列表
    """
    results = search_content(topic, top_k=2)
    if not results:
        return messages

    reference_text = "\n\n## 参考资料（来自教材库）\n\n"
    for r in results:
        # 截取前 800 字符，避免 Prompt 过长
        snippet = r["content"][:800]
        reference_text += (
            f"### {r['title']}（来源：{r.get('source_file', '未知')}）\n"
            f"{snippet}\n\n---\n\n"
        )
    reference_text += (
        "请基于以上参考资料生成学习材料，"
        "不要编造参考资料中没有的函数/概念。"
        "如果参考资料中没有相关内容，可以补充自己的知识，但要明确标注。"
    )

    # 注入到第一个 system 消息中
    new_messages = list(messages)
    for i, msg in enumerate(new_messages):
        if msg.get("role") == "system":
            new_messages[i] = {
                **msg,
                "content": msg["content"] + reference_text,
            }
            break
    else:
        # 没有 system 消息时，在开头插入
        new_messages.insert(0, {
            "role": "system",
            "content": reference_text.strip(),
        })

    logger.info(
        "ContentStore: 已为话题'%s'注入 %d 篇参考资料",
        topic, len(results)
    )
    return new_messages


def reload_content_store() -> int:
    """强制重新加载内容库（用于新增/更新教材后刷新）"""
    global _ready
    _ready = False
    return load_content_store()
