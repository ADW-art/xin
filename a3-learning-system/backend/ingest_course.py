#!/usr/bin/env python
"""
Python 课程知识库入库脚本
=======================

读取 python_course.json，将教材章节向量化存入 ChromaDB knowledge_base 集合，
将习题向量化存入 exercise_bank 集合，为 RAG 检索提供结构化课程内容。

用法:
    cd backend
    python ingest_course.py

依赖:
    - ChromaDB 服务已启动（Docker: a3-chromadb）
    - BGE-M3 模型已下载或可通过 HF mirror 下载
    - python_course.json 存在于 knowledge_materials/

入库策略:
    - 每个章节的每个小节作为独立文档 → knowledge_base
    - 每个习题作为独立文档 → exercise_bank
    - 元数据标注: course_code, chapter, section, type 等
"""

import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

# ═══════════════════════════════════════════════════════════
# CRITICAL: 必须在任何 HuggingFace 相关 import 之前设置
# ═══════════════════════════════════════════════════════════
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"

# 添加 backend 目录到 Python path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ingest_course")

# ═══════════════════════════════════════════════════════════
# 路径常量
# ═══════════════════════════════════════════════════════════
COURSE_JSON = os.path.join(
    BACKEND_DIR, "app", "scripts", "knowledge_materials", "python_course.json"
)
COURSE_CODE = "CS101"

# 集合名（与 rag_service 保持一致）
KB_COLLECTION = "knowledge_base"
EX_COLLECTION = "exercise_bank"


# ═══════════════════════════════════════════════════════════
# BGE 模型加载（独立于 rag_service，不受 HF_HUB_OFFLINE 影响）
# ═══════════════════════════════════════════════════════════

_dense_model = None


def load_embedding_model():
    """加载 BGE-M3 稠密向量模型"""
    global _dense_model
    import warnings
    warnings.filterwarnings("ignore")

    from app.config import settings

    model_name = getattr(settings, "embedding_model", "BAAI/bge-m3")
    local_path = getattr(settings, "embedding_local_path", "").strip()

    # 尝试本地路径优先
    if local_path and os.path.isdir(local_path):
        logger.info("从本地路径加载 BGE-M3: %s", local_path)
        from sentence_transformers import SentenceTransformer
        _dense_model = SentenceTransformer(
            local_path,
            device=settings.embedding_device,
            trust_remote_code=True,
        )
        logger.info("BGE-M3 本地加载完成")
        return _dense_model

    # 尝试从 HuggingFace 下载/加载
    logger.info("从 HuggingFace 加载 BGE-M3: %s (mirror: %s)", model_name, os.environ["HF_ENDPOINT"])
    logger.info("首次下载约需 2-5 分钟，请耐心等待...")

    import requests
    import urllib3
    urllib3.disable_warnings()
    from huggingface_hub import configure_http_backend

    def _hf_session():
        session = requests.Session()
        session.verify = False
        return session

    configure_http_backend(_hf_session)

    from sentence_transformers import SentenceTransformer

    _dense_model = SentenceTransformer(
        model_name,
        device=settings.embedding_device,
        trust_remote_code=True,
    )
    logger.info("BGE-M3 加载完成 (HF 模式), dim=%d", _dense_model.get_sentence_embedding_dimension())
    return _dense_model


def embed(texts: list[str]) -> list[list[float]]:
    """使用 BGE-M3 将文本列表转换为向量"""
    if _dense_model is None:
        raise RuntimeError("BGE 模型未加载，请先调用 load_embedding_model()")
    import numpy as np
    embeddings = _dense_model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    if isinstance(embeddings, np.ndarray):
        return embeddings.tolist()
    return [e.tolist() for e in embeddings]


# ═══════════════════════════════════════════════════════════
# ChromaDB 操作（使用 chroma_client 底层函数）
# ═══════════════════════════════════════════════════════════

def ingest_section(
    content: str,
    chapter_id: str,
    chapter_title: str,
    section_title: str,
    section_index: int,
    doc_id: str,
) -> bool:
    """将单个章节小节向量化后存入 knowledge_base"""
    from app.core.chroma_client import add_to_collection

    try:
        # 构造完整的检索文本：标题 + 内容
        full_text = f"【{COURSE_CODE}】{chapter_title} > {section_title}\n\n{content}"

        embedding = embed([full_text])[0]

        metadata = {
            "course_code": COURSE_CODE,
            "course_name": "Python程序设计基础",
            "chapter_id": chapter_id,
            "chapter_title": chapter_title,
            "section_title": section_title,
            "section_index": section_index,
            "source": f"{COURSE_CODE}/{chapter_id}",
            "doc_type": "course_section",
        }

        add_to_collection(
            name=KB_COLLECTION,
            documents=[full_text],
            metadatas=[metadata],
            ids=[doc_id],
            embeddings=[embedding],
        )

        # 同步写入 FAISS
        try:
            from app.services.faiss_client import get_faiss
            mgr = get_faiss()
            idx_name = mgr.route(COURSE_CODE)
            mgr.upsert(idx_name, [embedding], [full_text], [metadata])
        except Exception as e:
            logger.debug("FAISS 同步: %s", e)

        return True
    except Exception as e:
        logger.error("入库失败 %s: %s", doc_id, e)
        return False


def ingest_exercise(exercise: dict, chapter_id: str, chapter_title: str) -> bool:
    """将单个习题向量化后存入 exercise_bank"""
    from app.core.chroma_client import add_to_collection

    ex_id = exercise["id"]
    ex_type = exercise["type"]
    ex_text = exercise["question"]
    ex_answer = exercise.get("answer", "")
    ex_explain = exercise.get("explanation", "")
    ex_topic = exercise.get("topic", "")
    ex_difficulty = exercise.get("difficulty", "中等")
    ex_keywords = exercise.get("keywords", [])

    try:
        # 组合习题文本为统一格式（与 load_exercise_bank 格式一致）
        if ex_type == "choice":
            options = exercise.get("options", [])
            options_text = "\n".join(options)
            full_text = f"【{ex_type}】【{ex_difficulty}】{ex_text}\n{options_text}\n答案：{ex_answer}\n解析：{ex_explain}"
        elif ex_type == "fill":
            full_text = f"【{ex_type}】【{ex_difficulty}】{ex_text}\n答案：{ex_answer}\n解析：{ex_explain}"
        elif ex_type == "code":
            full_text = f"【{ex_type}】【{ex_difficulty}】{ex_text}\n参考答案：\n{ex_answer}\n解析：{ex_explain}"
        else:
            full_text = f"【{ex_type}】{ex_text}\n答案：{ex_answer}\n解析：{ex_explain}"

        embedding = embed([full_text])[0]

        metadata = {
            "type": ex_type,
            "difficulty": ex_difficulty,
            "topic": ex_topic,
            "chapter": chapter_title,
            "chapter_id": chapter_id,
            "course_code": COURSE_CODE,
            "keywords": ", ".join(ex_keywords) if ex_keywords else "",
            "source": f"{COURSE_CODE}_exercise_bank",
        }

        add_to_collection(
            name=EX_COLLECTION,
            documents=[full_text],
            metadatas=[metadata],
            ids=[ex_id],
            embeddings=[embedding],
        )

        return True
    except Exception as e:
        # 重复 ID 跳过
        if "already exists" in str(e) or "duplicate" in str(e).lower() or "IDAlreadyExists" in str(e):
            logger.debug("习题 %s 已存在，跳过", ex_id)
            return True  # 不算错误
        logger.error("习题入库失败 %s: %s", ex_id, e)
        return False


# ═══════════════════════════════════════════════════════════
# 统计查询
# ═══════════════════════════════════════════════════════════

def get_collection_counts():
    """查询各集合文档数"""
    from app.core.chroma_client import get_collection

    kb_count = 0
    ex_count = 0
    try:
        kb_col = get_collection(KB_COLLECTION)
        kb_count = kb_col.count()
    except Exception as e:
        logger.warning("knowledge_base 查询失败: %s", e)

    try:
        ex_col = get_collection(EX_COLLECTION)
        ex_count = ex_col.count()
    except Exception as e:
        logger.warning("exercise_bank 查询失败: %s", e)

    return kb_count, ex_count


def search_course(query: str, n: int = 3):
    """测试检索课程内容"""
    from app.core.chroma_client import search_in_collection

    try:
        q_emb = embed([query])[0]
        results = search_in_collection(KB_COLLECTION, q_emb, n=n)
        return results
    except Exception as e:
        logger.error("检索失败: %s", e)
        return {"documents": [], "metadatas": [], "distances": []}


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def main():
    logger.info("=" * 60)
    logger.info("Python 课程知识库入库脚本")
    logger.info("课程代码: %s", COURSE_CODE)
    logger.info("=" * 60)

    # 1. 检查 JSON 文件
    if not os.path.exists(COURSE_JSON):
        logger.error("课程文件不存在: %s", COURSE_JSON)
        sys.exit(1)
    logger.info("课程文件: %s", COURSE_JSON)

    # 2. 加载课程 JSON
    with open(COURSE_JSON, "r", encoding="utf-8") as f:
        course = json.load(f)

    course_name = course["course_name"]
    total_hours = course["total_hours"]
    chapters = course["chapters"]
    logger.info("课程名称: %s", course_name)
    logger.info("总学时: %d", total_hours)
    logger.info("章节数: %d", len(chapters))

    # 3. 加载 BGE 模型
    logger.info("--- 加载 BGE-M3 模型 ---")
    t0 = time.time()
    load_embedding_model()
    logger.info("模型加载耗时: %.1fs", time.time() - t0)

    # 4. 入库前统计
    kb_before, ex_before = get_collection_counts()
    logger.info("入库前: knowledge_base=%d, exercise_bank=%d", kb_before, ex_before)

    # 5. 逐章节入库
    total_sections = 0
    total_exercises = 0
    section_success = 0
    exercise_success = 0

    chapter_section_count = {}
    chapter_exercise_count = {}

    for ch in chapters:
        ch_id = ch["id"]
        ch_title = ch["title"]
        ch_hours = ch["hours"]
        sections = ch.get("sections", [])
        exercises = ch.get("exercises", [])

        logger.info("")
        logger.info("--- [%s] %s (%dh, %d节, %d题) ---",
                    ch_id, ch_title, ch_hours, len(sections), len(exercises))

        # 入库章节小节
        sec_count = 0
        for i, section in enumerate(sections):
            sec_title = section["title"]
            content = section["content"]
            doc_id = f"{COURSE_CODE.lower()}_{ch_id}_s{i+1:02d}"
            total_sections += 1

            logger.info("  入库章节: %s > %s (doc_id=%s, %d字)",
                        ch_title, sec_title, doc_id, len(content))

            if ingest_section(content, ch_id, ch_title, sec_title, i + 1, doc_id):
                section_success += 1
                sec_count += 1

        chapter_section_count[ch_id] = sec_count

        # 入库习题
        ex_count = 0
        for exercise in exercises:
            total_exercises += 1
            ex_id = exercise["id"]
            ex_q = exercise["question"][:40]

            logger.info("  入库习题: [%s/%s] %s...",
                        exercise["type"], exercise["difficulty"], ex_q)

            if ingest_exercise(exercise, ch_id, ch_title):
                exercise_success += 1
                ex_count += 1

        chapter_exercise_count[ch_id] = ex_count

    # 6. 入库后统计
    kb_after, ex_after = get_collection_counts()
    kb_added = kb_after - kb_before
    ex_added = ex_after - ex_before

    # 7. 验证检索
    logger.info("")
    logger.info("=" * 60)
    logger.info("入库完成")
    logger.info("=" * 60)
    logger.info("章节小节: 总计 %d, 成功 %d, 失败 %d",
                total_sections, section_success, total_sections - section_success)
    logger.info("习题:     总计 %d, 成功 %d, 失败 %d",
                total_exercises, exercise_success, total_exercises - exercise_success)
    logger.info("knowledge_base: %d → %d (+%d)", kb_before, kb_after, kb_added)
    logger.info("exercise_bank:  %d → %d (+%d)", ex_before, ex_after, ex_added)

    # 按章节汇总
    logger.info("")
    logger.info("--- 按章节汇总 ---")
    for ch in chapters:
        ch_id = ch["id"]
        logger.info("  %s %s: %d节, %d题",
                    ch_id, ch["title"],
                    chapter_section_count.get(ch_id, 0),
                    chapter_exercise_count.get(ch_id, 0))

    # 8. 检索验证
    logger.info("")
    logger.info("--- 检索验证 ---")
    test_queries = [
        "Python装饰器",
        "面向对象继承与多态",
        "文件读写操作",
        "异常处理try except",
    ]
    for q in test_queries:
        results = search_course(q, n=2)
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])
        if docs:
            title = ""
            if metas and len(metas) > 0:
                title = (metas[0] or {}).get("section_title", "")
            snippet = (docs[0] or "")[:60].replace("\n", " ")
            logger.info("  检索 '%s' → %s | %s...", q, title, snippet)
        else:
            logger.warning("  检索 '%s' → 无结果", q)

    # 9. exercise_bank 验证
    logger.info("")
    logger.info("--- 习题库验证 ---")
    from app.core.chroma_client import get_collection
    try:
        ex_col = get_collection(EX_COLLECTION)
        ex_data = ex_col.get()
        ex_ids = ex_data.get("ids", []) if ex_data else []
        course_ex_ids = [eid for eid in ex_ids if eid.startswith(COURSE_CODE.lower())]
        logger.info("exercise_bank 中 %s 课程习题: %d 个", COURSE_CODE, len(course_ex_ids))
    except Exception as e:
        logger.warning("习题库验证失败: %s", e)

    logger.info("")
    logger.info("✅ 课程知识库入库完成!")
    logger.info("   章节文档: %d 条 (知识检索)", section_success)
    logger.info("   习题文档: %d 条 (智能组卷)", exercise_success)

    return section_success, exercise_success


if __name__ == "__main__":
    main()
