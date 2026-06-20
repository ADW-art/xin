"""
RAG 知识库服务（企业级混合检索架构）

架构：
  1. 稠密向量召回 (BGE-M3 dense embedding + FAISS)
  2. BM25 稀疏召回 (BGE-M3 sparse embedding / rank_bm25)
  3. Cross-Encoder 精排 (BGE-Reranker-v2-m3)
  4. RRF 融合 (Reciprocal Rank Fusion)

三层知识库：
  - knowledge_base: 课本正文（教材内容检索）
  - exercise_bank: 习题题库（智能组卷素材）
  - concept_graph: 知识图谱（前置依赖关系）

使用方式：
  from app.services.rag_service import hybrid_search, ingest_document
  results = hybrid_search("Python装饰器", top_k=7)
"""

import json as _json
import logging
import os
import uuid
import warnings
from typing import Optional

import requests

from app.config import settings
# 根据配置设置 HF 镜像：为空则使用官方 HuggingFace
if settings.hf_mirror:
    os.environ["HF_ENDPOINT"] = settings.hf_mirror

from huggingface_hub import configure_http_backend
from app.core.chroma_client import add_to_collection, search_in_collection

# Lazy import: sentence_transformers depends on torch which may not be available
SentenceTransformer = None
CrossEncoder = None

def _lazy_import_st():
    """Lazily import sentence_transformers (depends on torch, may fail on some systems)"""
    global SentenceTransformer, CrossEncoder
    if SentenceTransformer is not None:
        return True
    try:
        from sentence_transformers import SentenceTransformer as _ST, CrossEncoder as _CE
        SentenceTransformer = _ST
        CrossEncoder = _CE
        return True
    except ImportError:
        return False

warnings.filterwarnings("ignore")

def _hf_session() -> requests.Session:
    """HuggingFace HTTP session — 直连绕过代理，默认启用 TLS"""
    session = requests.Session()
    session.trust_env = False
    session.proxies = {'http': None, 'https': None}
    if os.getenv("DEBUG_SKIP_TLS") == "1":
        session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return session

configure_http_backend(_hf_session)

logger = logging.getLogger(__name__)

# 模型单例
_dense_model: Optional[SentenceTransformer] = None
_reranker: Optional[CrossEncoder] = None
_embed_ready: bool = False  # BGE 就绪标志 — 未就绪时 Agent 跳过 RAG


def is_rag_ready() -> bool:
    """检查 RAG 是否就绪 (BGE 模型已加载)"""
    return _embed_ready

COLLECTION_NAME = "knowledge_base"
EXERCISE_COLLECTION = "exercise_bank"

# ============================================================
# 模型加载
# ============================================================

def _get_dense_model():
    """BGE-M3 稠密向量模型（优先本地路径，带重试机制）

    加载策略：
      1. embedding_local_path 非空且目录存在 → 直接从本地加载（最快）
      2. 否则 → 从 HF cache 或在线下载，最多重试3次（指数退避 1s/3s/9s）

    说明：单次请求失败不会永久跳过 RAG，下次请求会重新尝试加载。
    """
    if not _lazy_import_st():
        return None
    global _dense_model, _embed_ready
    if _dense_model is None and not _embed_ready:
        model_name = getattr(settings, 'embedding_model', 'BAAI/bge-m3')
        local_path = getattr(settings, 'embedding_local_path', '').strip()

        # ── 策略1：本地路径优先 ──
        if local_path and os.path.isdir(local_path):
            logger.info("RAG: 从本地路径加载 BGE-M3 %s ...", local_path)
            try:
                _dense_model = SentenceTransformer(local_path, device=settings.embedding_device, trust_remote_code=True)
                _embed_ready = True
                logger.info("RAG: BGE-M3 本地加载完成")
                return _dense_model
            except Exception as e:
                logger.warning("RAG: 本地路径加载失败，回退到 HF 模型名: %s", e)

        # ── 策略2：HF 模型名（最多重试3次，指数退避1s/3s/9s）──
        max_retries = 3
        import time as _time
        for attempt in range(1, max_retries + 1):
            logger.info("RAG: 加载 BGE-M3 %s (HF模式, 第 %d/%d 次)...", model_name, attempt, max_retries)
            try:
                _dense_model = SentenceTransformer(model_name, device=settings.embedding_device, trust_remote_code=True)
                _embed_ready = True
                logger.info("RAG: BGE-M3 加载完成 (HF模式, 第%d次成功)", attempt)
                return _dense_model
            except Exception as e:
                logger.warning("RAG: BGE-M3 加载失败 (第%d/%d次): %s", attempt, max_retries, e)
                if attempt < max_retries:
                    wait = 3 ** (attempt - 1)  # 1s, 3s, 9s
                    logger.info("RAG: %d秒后重试...", wait)
                    _time.sleep(wait)
                else:
                    logger.error("RAG: BGE-M3 加载最终失败，本次请求向量检索降级为跳过（下次请求将重试）")
                    _dense_model = None
    return _dense_model


def _get_reranker():
    """BGE-Reranker-v2-m3 交叉编码器（精排用）"""
    if not _lazy_import_st():
        return None
    global _reranker
    if _reranker is None:
        reranker_name = "BAAI/bge-reranker-v2-m3"
        logger.info("RAG: 加载 Reranker %s ...", reranker_name)
        _reranker = CrossEncoder(reranker_name, device=settings.embedding_device, trust_remote_code=True)
        logger.info("RAG: Reranker 加载完成")
    return _reranker


# ============================================================
# 向量化
# ============================================================

def _embed(texts: list[str]) -> list[list[float]]:
    """稠密向量化（BGE-M3），模型不可用时返回空列表"""
    model = _get_dense_model()
    if model is None:
        return []
    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()


# ============================================================
# BM25 稀疏召回
# ============================================================

_bm25_corpus: list[str] = []
_bm25_ready = False

try:
    from rank_bm25 import BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False


def _init_bm25():
    """初始化 BM25 索引（从 ChromaDB 加载所有文档）"""
    global _bm25_corpus, _bm25_ready
    if not _BM25_AVAILABLE or _bm25_ready:
        return
    try:
        from app.core.chroma_client import get_collection
        col = get_collection(COLLECTION_NAME)
        results = col.get()
        if results and results.get("documents"):
            import jieba
            _bm25_corpus = [" ".join(jieba.cut(doc)) for doc in results["documents"]]
            _bm25_ready = True
            logger.info("BM25: 索引初始化完成 %d 文档", len(_bm25_corpus))
    except Exception as e:
        logger.warning("BM25: 初始化失败 %s", e)


def _bm25_search(query: str, top_k: int = 30) -> list[tuple[int, float]]:
    """BM25 稀疏检索 → [(doc_index, score), ...]"""
    if not _BM25_AVAILABLE or not _bm25_ready:
        return []
    try:
        import jieba
        tokenized = " ".join(jieba.cut(query))
        bm25 = BM25Okapi([doc.split() for doc in _bm25_corpus])
        scores = bm25.get_scores(tokenized.split())
        ranked = sorted(enumerate(scores), key=lambda x: x[1] or 0, reverse=True)
        return [(idx, float(s) if s is not None else 0.0) for idx, s in ranked[:top_k]]
    except Exception as e:
        logger.warning("BM25: 检索失败 %s", e)
        return []


# ============================================================
# RRF 融合
# ============================================================

def _rrf_fusion(dense_results: list[dict], bm25_results: list[dict], k: int = 60):
    """Reciprocal Rank Fusion：合并稠密和稀疏的排序结果"""
    scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for rank, doc in enumerate(dense_results):
        doc_id = doc.get("id", str(rank))
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
        doc_map[doc_id] = doc

    for rank, doc in enumerate(bm25_results):
        doc_id = doc.get("id", str(rank + 10000))
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
        doc_map[doc_id] = doc

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_map[did] for did, _ in ranked]


def _faiss_dense_search(query_emb: list[float], top_k: int = 30) -> list[dict]:
    """FAISS 稠密向量检索：从所有子索引中检索并合并结果"""
    try:
        from app.services.faiss_client import get_faiss
        mgr = get_faiss()
        all_results = []
        for idx_name in mgr.indices:
            results = mgr.search(query_emb, subject=idx_name, top_k=top_k)
            all_results.extend(results)
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results[:top_k]
    except Exception as e:
        logger.warning("FAISS 稠密召回不可用: %s", e)
        return []


# ============================================================
# 混合检索（稠密 + BM25 + Reranker 三路融合）
# ============================================================

def hybrid_search(query: str, top_k: int = 7, use_reranker: bool = True) -> list[dict]:
    """三路融合检索：稠密召回 + BM25召回 + CrossEncoder精排 → Top-K

    返回：[{"content": "...", "score": 0.92, "metadata": {...}}, ...]
    """
    results = []

    # ① 稠密向量召回 Top-30（优先 FAISS，降级 ChromaDB）
    try:
        q_emb = _embed([query])[0]
        faiss_results = _faiss_dense_search(q_emb, top_k=30)
        if faiss_results:
            results = faiss_results
            logger.info("混合检索: FAISS稠密召回 %d 条", len(results))
        else:
            # 降级到 ChromaDB
            chroma_results = search_in_collection(COLLECTION_NAME, q_emb, n=30)
            for i in range(len(chroma_results["documents"])):
                results.append({
                    "id": f"dense_{i}",
                    "content": chroma_results["documents"][i],
                    "metadata": chroma_results["metadatas"][i] if chroma_results["metadatas"] else {},
                    "score": 1.0 - chroma_results["distances"][i] if chroma_results["distances"] else 0.5,
                    "source": "dense_chromadb",
                })
            logger.info("混合检索: FAISS不可用，降级到ChromaDB")
    except Exception as e:
        logger.warning("混合检索-稠密召回失败: %s", e)

    # ② BM25 稀疏召回 Top-30
    bm25_results = []
    try:
        _init_bm25()
        bm25_hits = _bm25_search(query, top_k=30)
        from app.core.chroma_client import get_collection
        col = get_collection(COLLECTION_NAME)
        all_docs = col.get()
        for idx, score in bm25_hits:
            if all_docs and idx < len(all_docs.get("documents", [])):
                bm25_results.append({
                    "id": f"bm25_{idx}",
                    "content": all_docs["documents"][idx],
                    "metadata": all_docs["metadatas"][idx] if all_docs.get("metadatas") and idx < len(all_docs["metadatas"]) else {},
                    "score": score / max(s for _, s in bm25_hits) if bm25_hits else 0.5,
                    "source": "bm25",
                })
    except Exception as e:
        logger.warning("混合检索-BM25召回失败: %s", e)

    # ③ RRF 融合
    fused = _rrf_fusion(results, bm25_results)
    candidates = fused[:15]

    # ④ Cross-Encoder 精排
    if use_reranker and len(candidates) > top_k:
        try:
            reranker = _get_reranker()
            pairs = [[query, c["content"][:512]] for c in candidates]
            ce_scores = reranker.predict(pairs, show_progress_bar=False)
            for c, s in zip(candidates, ce_scores):
                c["score"] = float(s) if s is not None else 0.0
            candidates.sort(key=lambda x: x["score"], reverse=True)
        except Exception as e:
            logger.warning("混合检索-Reranker精排失败: %s", e)

    return candidates[:top_k]


# ============================================================
# RAG 流水线追踪（供前端 RagCenter 可视化）
# ============================================================

def rag_trace(query: str) -> dict:
    """运行完整 RAG 流水线并返回各阶段中间结果，用于可视化展示

    返回结构：
    {
      "query": "...",
      "pipeline": {
        "dense_recall": [{"content": "...", "score": 0.85, "source": "dense_faiss"}, ...],
        "bm25_recall":  [{"content": "...", "score": 0.72, "source": "bm25"}, ...],
        "rrf_fused":    [{"content": "...", "score": 0.018, "source": "..."}, ...],
        "reranked":     [{"content": "...", "score": 0.95, "source": "..."}, ...],
      },
      "stage_times": {"dense_ms": 12, "bm25_ms": 8, "rerank_ms": 45},
      "kb_total": 1234,
      "latency_ms": 234,
    }
    """
    import time as _time

    result: dict = {
        "query": query,
        "pipeline": {
            "dense_recall": [],
            "bm25_recall": [],
            "rrf_fused": [],
            "reranked": [],
        },
        "stage_times": {"dense_ms": 0, "bm25_ms": 0, "rerank_ms": 0},
        "kb_total": get_knowledge_count(),
        "latency_ms": 0,
    }

    t_start = _time.time()

    # ── Stage 1: Dense Recall ──
    t0 = _time.time()
    dense_results: list[dict] = []
    try:
        q_emb_list = _embed([query])
        if q_emb_list:
            q_emb = q_emb_list[0]
            faiss_hits = _faiss_dense_search(q_emb, top_k=10)
            if faiss_hits:
                dense_results = [
                    {
                        "content": h["content"][:300],
                        "score": round(float(h.get("score", 0)), 4),
                        "source": h.get("source", "dense_faiss"),
                    }
                    for h in faiss_hits
                ]
            else:
                # ChromaDB 降级
                chroma_hits = search_in_collection(COLLECTION_NAME, q_emb, n=10)
                for i in range(len(chroma_hits.get("documents", []))):
                    dist = chroma_hits["distances"][i] if chroma_hits.get("distances") else 0
                    dense_results.append({
                        "content": chroma_hits["documents"][i][:300],
                        "score": round(1.0 - dist, 4) if dist else 0.5,
                        "source": "dense_chromadb",
                    })
    except Exception as e:
        logger.warning("rag_trace: dense recall failed: %s", e)
    result["stage_times"]["dense_ms"] = int((_time.time() - t0) * 1000)

    # ── Stage 2: BM25 Sparse Recall ──
    t0 = _time.time()
    bm25_results: list[dict] = []
    try:
        _init_bm25()
        bm25_hits = _bm25_search(query, top_k=10)
        if bm25_hits:
            from app.core.chroma_client import get_collection
            col = get_collection(COLLECTION_NAME)
            all_docs = col.get()
            doc_list = all_docs.get("documents", []) if all_docs else []
            max_s = max(s for _, s in bm25_hits) if bm25_hits else 1.0
            for idx, score in bm25_hits:
                if idx < len(doc_list):
                    bm25_results.append({
                        "content": doc_list[idx][:300],
                        "score": round(score / max_s, 4) if max_s > 0 else 0.0,
                        "source": "bm25",
                    })
    except Exception as e:
        logger.warning("rag_trace: BM25 recall failed: %s", e)
    result["stage_times"]["bm25_ms"] = int((_time.time() - t0) * 1000)

    # ── Stage 3: RRF Fusion ──
    fused: list[dict] = _rrf_fusion(dense_results, bm25_results)

    # ── Stage 4: CrossEncoder Rerank ──
    t0 = _time.time()
    reranked = list(fused[:10])
    try:
        if len(fused) > 3:
            reranker = _get_reranker()
            pairs = [[query, c["content"][:512]] for c in fused[:10]]
            ce_scores = reranker.predict(pairs, show_progress_bar=False)
            for c, s in zip(fused[:10], ce_scores):
                c["score"] = round(float(s) if s is not None else 0.0, 4)
            reranked = sorted(fused[:10], key=lambda x: x.get("score", 0), reverse=True)
    except Exception as e:
        logger.warning("rag_trace: reranker failed: %s", e)
    result["stage_times"]["rerank_ms"] = int((_time.time() - t0) * 1000)

    # ── 组装结果 ──
    # 截断内容便于前端展示
    for item in dense_results:
        item["content"] = item["content"][:300]
    for item in bm25_results:
        item["content"] = item["content"][:300]
    for item in fused:
        item["content"] = item.get("content", "")[:300]
    for item in reranked:
        item["content"] = item.get("content", "")[:300]

    result["pipeline"]["dense_recall"] = dense_results
    result["pipeline"]["bm25_recall"] = bm25_results
    result["pipeline"]["rrf_fused"] = fused[:15]
    result["pipeline"]["reranked"] = reranked[:5]
    result["latency_ms"] = int((_time.time() - t_start) * 1000)

    # ── v4: Stage summaries for Cursor-style trace UI ──
    def _score_stats(items: list[dict]) -> dict:
        if not items: return {"min": 0, "max": 0, "avg": 0, "top3_avg": 0}
        scores = [it.get("score", 0) for it in items]
        return {
            "min": round(min(scores), 4),
            "max": round(max(scores), 4),
            "avg": round(sum(scores) / len(scores), 4),
            "top3_avg": round(sum(sorted(scores, reverse=True)[:3]) / min(3, len(scores)), 4),
        }

    result["stage_summary"] = [
        {
            "id": "dense", "name": "Dense 语义召回", "icon": "Connection",
            "count": len(dense_results), "time_ms": result["stage_times"]["dense_ms"],
            "stats": _score_stats(dense_results),
        },
        {
            "id": "bm25", "name": "BM25 关键词召回", "icon": "Search",
            "count": len(bm25_results), "time_ms": result["stage_times"]["bm25_ms"],
            "stats": _score_stats(bm25_results),
        },
        {
            "id": "rrf", "name": "RRF 排名融合", "icon": "Operation",
            "count": min(len(fused), 15), "time_ms": 0,
            "stats": _score_stats(fused),
        },
        {
            "id": "rerank", "name": "CrossEncoder 精排", "icon": "TrendCharts",
            "count": min(len(reranked), 5), "time_ms": result["stage_times"]["rerank_ms"],
            "stats": _score_stats(reranked),
        },
    ]

    # Score improvement: how much Reranker improves over RRF
    if fused and reranked:
        fused_best = fused[0].get("score", 0) if fused else 0
        rerank_best = reranked[0].get("score", 0) if reranked else 0
        result["improvement"] = {
            "rrf_to_rerank": round((rerank_best - fused_best) * 100, 1) if fused_best else 0,
            "description": f"精排使最佳结果分数从{fused_best:.3f}提升至{rerank_best:.3f}",
        }
    else:
        result["improvement"] = {"rrf_to_rerank": 0, "description": ""}

    return result


# ============================================================
# 习题题库加载
# ============================================================

def load_exercise_bank(file_path: str = None):
    """从 JSON 文件加载习题库并向量化入库"""
    import json as _json_lib
    import os as _os
    if file_path is None:
        file_path = _os.path.join(_os.path.dirname(__file__), "..", "scripts", "knowledge_materials", "exercise_bank.json")
    if not _os.path.exists(file_path):
        logger.warning("习题库文件不存在: %s", file_path)
        return 0
    with open(file_path, "r", encoding="utf-8") as f:
        data = _json_lib.load(f)
    exercises = data.get("exercises", [])
    count = 0
    for ex in exercises:
        text = f"【{ex['type']}】{ex['question']}\n答案：{ex['answer']}\n解析：{ex['explanation']}"
        embed = _embed([text])[0]
        meta = {"type": ex["type"], "difficulty": ex["difficulty"], "topic": ex["topic"], "chapter": ex["chapter"], "keywords": ", ".join(ex.get("keywords", [])), "source": "exercise_bank"}
        try:
            add_to_collection(EXERCISE_COLLECTION, [text], [meta], [ex["id"]], [embed])
            count += 1
        except Exception as e:
            # 重复 ID → 跳过
            logger.debug("习题 %s 已存在", ex["id"])
    logger.info("习题库: 加载 %d 题", count)
    return count


def search_exercises(query: str, difficulty: str = None, n: int = 5) -> list[dict]:
    """从习题题库检索相关题目"""
    q_emb = _embed([query])[0]
    try:
        results = search_in_collection(EXERCISE_COLLECTION, q_emb, n=n * 2 if difficulty else n)
        docs = []
        for i in range(len(results["documents"])):
            meta = (results["metadatas"][i] if results["metadatas"] and i < len(results["metadatas"]) else {}) or {}
            if difficulty and meta.get("difficulty") != difficulty:
                continue
            docs.append({
                "content": results["documents"][i] or "",
                "metadata": meta,
                "score": 1 - results["distances"][i] if results["distances"] else 0.5,
            })
            if len(docs) >= n:
                break
        return docs
    except Exception:
        return []


# ============================================================
# 文档导入 / 检索 / 重排序
# ============================================================

def ingest_document(
    content: str,
    title: str = "",
    source: str = "",
    doc_id: str | None = None,
) -> str:
    """将单篇文档向量化后存入 ChromaDB

    参数：
      content:  文档正文
      title:    文档标题
      source:   文档来源
      doc_id:   自定义 ID，不传则自动生成 UUID

    返回：
      存入的文档 ID
    """
    doc_id = doc_id or str(uuid.uuid4())
    embedding = _embed([content])[0]

    add_to_collection(
        name=COLLECTION_NAME,
        documents=[content],
        metadatas=[{"title": title, "source": source}],
        ids=[doc_id],
        embeddings=[embedding],
    )

    # 同步写入 FAISS
    try:
        from app.services.faiss_client import get_faiss
        faiss_meta = {"title": title, "source": source}
        mgr = get_faiss()
        idx_name = mgr.route(source)
        mgr.upsert(idx_name, [embedding], [content], [faiss_meta])
    except Exception as e:
        logger.warning("FAISS 同步写入失败: %s", e)

    logger.info("RAGService: 文档已入库 id=%s title=%s", doc_id, title)
    return doc_id

#2.检索相似
def search_knowledge(query: str, n: int = 3) -> list[dict]:
    """检索与查询文本最相似的 n 条知识

    参数：
      query:  查询文本
      n:      返回结果数量

    返回：
      [{"content": "...", "metadata": {...}, "score": 0.95}, ...]
    """
    query_embedding = _embed([query])[0]
    results = search_in_collection(COLLECTION_NAME, query_embedding, n=n)

    docs = []
    for i in range(len(results["documents"])):
        content = results["documents"][i] or ""
        docs.append({
            "content": content,
            "metadata": (results["metadatas"][i] if results["metadatas"] and i < len(results["metadatas"]) else {}) or {},
            "score": 1 - results["distances"][i] if results["distances"] and i < len(results["distances"]) else 0,
        })

    return docs

def rerank(query: str, candidates: list[dict], top_n: int = 3) -> list[dict]:
    """重排序：用 BGE-Reranker-v2-m3 CrossEncoder 精排候选文档

    比 LLM 重排更快、更稳定、无 API 开销。是工业级 RAG 的标准做法。
    """
    if len(candidates) <= top_n:
        return candidates

    try:
        reranker = _get_reranker()
        pairs = [[query, c["content"][:512]] for c in candidates]
        ce_scores = reranker.predict(pairs, show_progress_bar=False)
        for c, s in zip(candidates, ce_scores):
            c["score"] = float(s) if s is not None else 0.0
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_n]
    except Exception as e:
        logger.warning("Reranker 精排失败: %s", e)
        return candidates[:top_n]


def retrieve_context(query: str, n: int = 3, timeout: float = 15.0) -> str:
    """检索 + 重排序 → 拼成带引用的 Prompt 上下文字符串

    使用线程池超时控制，防止 BGE 模型首次加载阻塞太久（默认 15s）
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

    def _retrieve():
        candidates = search_knowledge(query, n=5)
        if not candidates:
            return ""
        results = rerank(query, candidates, top_n=n)
        parts = []
        for r in results:
            src = r["metadata"].get("source", "未知来源")
            parts.append(f"[来源：{src}]\n{r['content']}")
        return "\n\n---\n\n".join(parts)

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_retrieve)
            return future.result(timeout=timeout)
    except FutureTimeout:
        logger.warning("RAG 检索超时 (%.0fs)，降级为纯 LLM 生成", timeout)
        return ""
    except Exception as e:
        logger.warning("RAG 检索异常: %s", e)
        return ""

#3.数量
def get_knowledge_count() -> int:
    """获取知识库中的文档总数"""
    from app.core.chroma_client import get_collection
    col = get_collection(COLLECTION_NAME)
    return col.count()
