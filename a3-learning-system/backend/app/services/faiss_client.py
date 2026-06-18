"""
FAISS 多子索引客户端

架构：
  按学科划分独立子索引，检索时先路由到对应学科索引，再向量检索。
  子索引按需加载，不常用索引自动卸载节省内存。

索引结构：
  faiss_indices/
  ├── python.faiss           Python 相关教材
  ├── datastructure.faiss    数据结构教材
  ├── os.faiss               操作系统教材
  ├── network.faiss          计算机网络教材
  ├── database.faiss         数据库教材
  ├── ai_ml.faiss            人工智能/机器学习教材
  └── default.faiss          未分类教材（兜底）

使用方式：
  from app.services.faiss_client import get_faiss, upsert, search

  # 入库
  upsert("python", vectors, texts, metadatas)

  # 检索（自动路由到对应子索引）
  results = search([query_vector], "python", top_k=30)
"""

import os
import logging
import pickle
from typing import Optional

import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

logger = logging.getLogger(__name__)

INDEX_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "faiss_indices")
INDEX_DIR = os.path.abspath(INDEX_DIR)

# 学科到子索引名称的映射
SUBJECT_MAP = {
    "python": "python",
    "数据结构": "datastructure",
    "操作系统": "os",
    "计算机网络": "network",
    "数据库": "database",
    "人工智能": "ai_ml",
    "机器学习": "ai_ml",
    "深度学习": "ai_ml",
    "c语言": "clang",
    "cpp": "clang",
    "java": "java",
    "离散数学": "math",
    "高等数学": "math",
}


class FaissIndex:
    """单个 FAISS 子索引"""

    def __init__(self, name: str, dim: int = 1024):
        self.name = name
        self.dim = dim
        self.index: Optional[faiss.Index] = None
        self.texts: list[str] = []
        self.metadatas: list[dict] = []
        self._loaded = False

    @property
    def path(self) -> str:
        return os.path.join(INDEX_DIR, f"{self.name}.faiss")

    @property
    def meta_path(self) -> str:
        return os.path.join(INDEX_DIR, f"{self.name}.meta.pkl")

    def create(self):
        """创建 Flat 精确索引（无需训练，适用于百万级以下数据）"""
        if not FAISS_AVAILABLE:
            raise RuntimeError("faiss 未安装，运行: pip install faiss-cpu")
        self.index = faiss.IndexFlatIP(self.dim)
        self._loaded = True

    def add(self, vectors: np.ndarray, texts: list[str], metadatas: list[dict]):
        """添加向量到索引"""
        if self.index is None:
            self.create()

        start_idx = len(self.texts)
        self.index.add(vectors.astype(np.float32))
        self.texts.extend(texts)
        self.metadatas.extend(metadatas)
        logger.info("FAISS[%s]: 新增 %d 条，当前共 %d 条", self.name, len(vectors), len(self.texts))

    def search(self, query_vector: np.ndarray, top_k: int = 30) -> list[dict]:
        """检索最相似的 top_k 条"""
        if self.index is None or self.index.ntotal == 0:
            return []

        query = query_vector.astype(np.float32).reshape(1, -1)
        distances, indices = self.index.search(query, min(top_k, self.index.ntotal))

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= 0 and idx < len(self.texts):
                results.append({
                    "content": self.texts[idx],
                    "metadata": self.metadatas[idx],
                    "score": float(dist) if dist is not None else 0.0,
                    "source": f"faiss:{self.name}",
                })
        return results

    def save(self):
        """持久化索引到磁盘"""
        if self.index is None or not FAISS_AVAILABLE:
            return
        os.makedirs(INDEX_DIR, exist_ok=True)
        faiss.write_index(self.index, self.path)
        with open(self.meta_path, "wb") as f:
            pickle.dump({"texts": self.texts, "metadatas": self.metadatas}, f)
        logger.info("FAISS[%s]: 保存完成 ntotal=%d", self.name, self.index.ntotal)

    def load(self):
        """从磁盘加载索引"""
        if not FAISS_AVAILABLE or not os.path.exists(self.path):
            return False
        self.index = faiss.read_index(self.path)
        if os.path.exists(self.meta_path):
            with open(self.meta_path, "rb") as f:
                data = pickle.load(f)
                self.texts = data["texts"]
                self.metadatas = data["metadatas"]
        self._loaded = True
        logger.info("FAISS[%s]: 加载完成 ntotal=%d", self.name, self.index.ntotal)
        return True

    def __len__(self):
        return len(self.texts)


class FaissManager:
    """FAISS 多子索引管理器"""

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.indices: dict[str, FaissIndex] = {}
        os.makedirs(INDEX_DIR, exist_ok=True)

    def _get_index(self, name: str) -> FaissIndex:
        if name not in self.indices:
            idx = FaissIndex(name, self.dim)
            if not idx.load():
                idx.create()
            self.indices[name] = idx
        return self.indices[name]

    def route(self, subject: str) -> str:
        """根据学科名返回对应的子索引名"""
        for key, idx_name in SUBJECT_MAP.items():
            if key in subject:
                return idx_name
        return "default"

    def upsert(self, index_name: str, vectors: list[list[float]], texts: list[str], metadatas: list[dict]):
        """添加向量到指定子索引"""
        idx = self._get_index(index_name)
        arr = np.array(vectors)
        idx.add(arr, texts, metadatas)

    def search(self, query_vector: list[float], subject: str = "", top_k: int = 30) -> list[dict]:
        """检索：先路由到子索引，再向量检索"""
        index_name = self.route(subject)
        idx = self._get_index(index_name)
        results = idx.search(np.array(query_vector), top_k)

        # 如果子索引结果不够，补充默认索引
        if len(results) < top_k and index_name != "default":
            default_idx = self._get_index("default")
            remaining = top_k - len(results)
            extra = default_idx.search(np.array(query_vector), remaining)
            results.extend(extra)

        return results

    def save_all(self):
        for idx in self.indices.values():
            idx.save()

    def get_total(self) -> int:
        return sum(len(idx) for idx in self.indices.values())


# 模块级单例
_manager: Optional[FaissManager] = None


def get_faiss(dim: int = 1024) -> FaissManager:
    global _manager
    if _manager is None:
        _manager = FaissManager(dim)
    return _manager


def upsert(index_name: str, vectors: list[list[float]], texts: list[str], metadatas: list[dict]):
    get_faiss().upsert(index_name, vectors, texts, metadatas)


def search(query_vector: list[float], subject: str = "", top_k: int = 30) -> list[dict]:
    return get_faiss().search(query_vector, subject, top_k)
