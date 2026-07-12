'''
ChromaDB 向量数据库客户端

功能：
  连接 Docker 中的 ChromaDB 服务，管理 Collection（创建/读取）
  提供向量的添加（add）和检索（query）功能

使用方式：
  from app.core.chroma_client import get_collection, add_to_collection, search_in_collection

  # 添加文档
  add_to_collection("knowledge_base", documents=["文本1", "文本2"], metadatas=[...], ids=[...], embeddings=[...])

  # 检索
  results = search_in_collection("knowledge_base", query_embedding=[0.1, 0.2, ...], n=3)
'''
# ── 静音 ChromaDB telemetry 警告（业内标准 4 层防护）──
# 必须在 import chromadb 之前执行
import os as _os
_os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
_os.environ.setdefault("CHROMA_TELEMETRY_DISABLED", "True")
_os.environ.setdefault("POSTHOG_DISABLED", "True")

import logging as _logging
import threading as _threading
# 拦截 posthog / chromadb.telemetry 的 logger，ERROR 以下全部丢弃
_telemetry_loggers = [
    "chromadb", "chromadb.telemetry", "chromadb.telemetry.product",
    "posthog", "posthog.analytics",
]
for _name in _telemetry_loggers:
    _lg = _logging.getLogger(_name)
    _lg.setLevel(_logging.CRITICAL + 1)
    _lg.disabled = True
    _lg.propagate = False

logger = _logging.getLogger(__name__)

# Monkey-patch posthog.capture：让 chromadb 内部的 telemetry 调用静默返回
try:
    import posthog as _posthog  # type: ignore
    _posthog.capture = lambda *args, **kwargs: None
except Exception:
    pass

import chromadb
from chromadb.config import Settings as ChromaSettings
from app.config import settings as _settings

_client = None
_collections: dict[str, any] = {}
_lock = _threading.RLock()  # P1-5: RLock 支持重入, 避免 get_collection → get_client 死锁

#建立连接
def get_client():
    """获取 ChromaDB 客户端（单例模式，优先 HTTP，PersistentClient 兜底）

    P1-4 (2026-07-12): 优先 HTTP client (Docker:8000)，避免 PersistentClient
    打开大 sqlite3 文件 (969MB+) 时阻塞整个 asyncio event loop。
    """
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                # 优先 HTTP client (Docker ChromaDB on :8000)
                try:
                    _client = chromadb.HttpClient(
                        host="localhost",
                        port=8000,
                        settings=ChromaSettings(anonymized_telemetry=False),
                    )
                    logger.info("ChromaDB: HttpClient 初始化成功 localhost:8000")
                except Exception as e:
                    # 兜底: PersistentClient（本地文件存储）
                    logger.warning("ChromaDB: HttpClient 失败(%s), 降级到 PersistentClient", e)
                    import os
                    local_path = _settings.chroma_persist_dir or os.path.join(os.path.dirname(__file__), "..", "..", "chroma_data_local")
                    local_path = os.path.abspath(local_path)
                    _client = chromadb.PersistentClient(
                        path=local_path,
                        settings=ChromaSettings(anonymized_telemetry=False),
                    )
                    logger.info("ChromaDB: PersistentClient 初始化成功 path=%s", local_path)
    return _client

#创建知识库
def get_collection(name: str):
    """获取或创建 Collection（按名称缓存，线程安全）"""
    if name not in _collections:
        with _lock:
            if name not in _collections:
                client = get_client()
                try:
                    _collections[name] = client.get_collection(name)    # 已存在 → 获取
                    logger.debug("ChromaDB: 获取已有 collection '%s'", name)
                except Exception as e:
                    logger.warning("ChromaDB: get_collection('%s') 失败(%s), 尝试创建", name, e)
                    try:
                        _collections[name] = client.create_collection(name)  # 不存在 → 创建
                        logger.info("ChromaDB: 创建新 collection '%s'", name)
                    except Exception as e2:
                        # P0-FIX: 并发创建冲突 → 直接获取（不再静默吞错）
                        logger.warning("ChromaDB: create_collection('%s') 失败(%s), 尝试并发获取", name, e2)
                        _collections[name] = client.get_collection(name)
    return _collections[name]

#1.批量添加指定文档
def add_to_collection(
    name: str,
    documents: list[str],
    metadatas: list[dict],
    ids: list[str],
    embeddings: list[list[float]],
):
    """批量添加文档到指定 Collection

    设计: 使用 upsert 语义（参考 ChromaDB 官方推荐做法）
    - 遇到新 ID → add
    - 遇到已存在 ID → update
    - 避免 "Insert/Add of existing embedding ID" 警告刷屏
    """
    col = get_collection(name)
    # 静默 chromadb 的重复 ID 警告（业内方案：调用 .upsert 替代 .add）
    # chromadb 默认会对重复 ID 输出 stderr 警告（"Insert/Add of existing embedding ID"）
    # 但这些是预期行为，不影响功能，仅做信息性提示
    col.upsert(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
        embeddings=embeddings,
    )

#2.检索相似
def search_in_collection(name: str, query_embedding: list[float], n: int = 3) -> dict:
    """在 Collection 中检索与查询向量最相似的 n 条文档"""
    col = get_collection(name)
    results = col.query(query_embeddings=[query_embedding], n_results=n)
    # P0-FIX: 防护 0 结果时 IndexError — results["documents"] 可能是空列表
    docs = results.get("documents", [[]])
    metas = results.get("metadatas", [[]])
    dists = results.get("distances", [[]])
    return {
        "documents": docs[0] if docs else [],
        "metadatas": metas[0] if metas else [],
        "distances": dists[0] if dists else [],
    }

#3.删除
def delete_collection(name: str):
    """删除 Collection（用于重置知识库）"""
    client = get_client()
    try:
        client.delete_collection(name)
    except Exception:
        pass
    _collections.pop(name, None)
