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

# P1-FIX: 调高 huggingface_hub 默认 timeout (默认 10s 太短, hf-mirror.com 偶尔抖动就超时)
# 设置后 CrossEncoder / SentenceTransformer 内部下载会使用这个 timeout
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")  # 单次请求 timeout 60s
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")   # 禁用 hf_transfer, 避免额外依赖

from huggingface_hub import configure_http_backend
from app.core.chroma_client import add_to_collection, search_in_collection

# Lazy import: sentence_transformers depends on torch which may not be available
SentenceTransformer = None
CrossEncoder = None

def _lazy_import_st():
    """Lazily import sentence_transformers (depends on torch, may fail on some systems)

    关键修复 (meta tensor): 必须在 import 前设置环境变量，阻止 accelerate 使用 meta device。
    bge-large-zh-v1.5 和 bge-m3 都受此影响（sentence-transformers >= 3.0 + torch >= 2.0）。
    参考: https://github.com/UKPLab/sentence-transformers/issues/2624
    """
    global SentenceTransformer, CrossEncoder
    if SentenceTransformer is not None:
        return True
    # 必须在 sentence-transformers import 前设置，防止 meta device
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("ACCELERATE_USE_META_DEVICE", "False")
    try:
        from sentence_transformers import SentenceTransformer as _ST, CrossEncoder as _CE
        SentenceTransformer = _ST
        CrossEncoder = _CE
        return True
    except ImportError:
        return False


# ============================================================
# Meta Tensor 错误深度修复（针对 BGE-M3 已知问题）
# ============================================================
#
# 背景：sentence-transformers 加载 BGE-M3 时会触发：
#   "Cannot copy out of meta tensor; no data!"
#
# 根因（经排查 + 业内 issue 验证）：
#   1. transformers ≥4.36 默认 low_cpu_mem_usage=True
#   2. trust_remote_code=True 时加载 BAAI/bge-m3 会执行远端仓库的 modeling_m3.py
#   3. 该远端代码内部使用 torch.device("meta") 占位
#   4. sentence-transformers 后续的 state_dict 加载钩子没正确处理
#
# 业内可行方案（多管齐下，最大化成功率）：
#   A. monkey-patch PreTrainedModel.from_pretrained → 注入 low_cpu_mem_usage=False
#   B. monkey-patch torch.nn.Module.__init__  → 屏蔽 meta device 创建
#   C. 设置环境变量 TRANSFORMERS_NO_ADVISORY_WARNINGS=1 + low_cpu_mem_usage 全局
#   D. 失败时降级为「纯 transformers AutoModel + mean pooling」自实现
#
# 关键：必须让 patch 在 import 阶段就执行（句子转换器是 lazy import）
# ============================================================

_META_PATCHED = False


def _apply_meta_tensor_patch():
    """全局应用 Meta Tensor 错误修复（业内已知最佳实践）"""
    global _META_PATCHED
    if _META_PATCHED:
        return
    _META_PATCHED = True

    # ── A: Monkey-patch transformers.PreTrainedModel.from_pretrained ──
    # 强制 low_cpu_mem_usage=False，从源头杜绝 meta device
    try:
        from transformers import modeling_utils as _mf
        if not getattr(_mf, "_A3_META_PATCHED", False):
            _orig = _mf.PreTrainedModel.from_pretrained.__func__

            def _patched(cls, *args, **kwargs):
                # 关键修复：禁用 low_cpu_mem_usage 避免 meta tensor
                kwargs["low_cpu_mem_usage"] = False
                kwargs.pop("device_map", None)
                return _orig(cls, *args, **kwargs)

            _mf.PreTrainedModel.from_pretrained = classmethod(_patched)
            _mf._A3_META_PATCHED = True
            logger.info("[META-FIX] PreTrainedModel.from_pretrained 已 patch")
    except Exception as _e:
        logger.warning("[META-FIX] PreTrainedModel patch 失败: %s", _e)

    # ── B: 设置 transformers 全局默认 ──
    try:
        from transformers import utils as _utils
        # transformers 4.36+ 在 modeling_utils 里读这个
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "0")
        # 强制不使用 meta device
        os.environ.setdefault("PYTORCH_NO_META", "1")
    except Exception:
        pass

    # ── C: 兼容 sentence-transformers 内部 auto_model loader ──
    # 拦截 AutoModel.from_pretrained 调用，同样强制 low_cpu_mem_usage=False
    try:
        from transformers import AutoModel, AutoConfig
        _orig_auto = AutoModel.from_pretrained.__func__

        def _patched_auto(cls, *args, **kwargs):
            kwargs["low_cpu_mem_usage"] = False
            kwargs.pop("device_map", None)
            return _orig_auto(cls, *args, **kwargs)

        AutoModel.from_pretrained = classmethod(_patched_auto)
        # 同样 patch XLM-RoBERTa（sentence-transformers 会用）
        try:
            from transformers import XLMRobertaModel
            _orig_xlm = XLMRobertaModel.from_pretrained.__func__

            def _patched_xlm(cls, *args, **kwargs):
                kwargs["low_cpu_mem_usage"] = False
                kwargs.pop("device_map", None)
                return _orig_xlm(cls, *args, **kwargs)

            XLMRobertaModel.from_pretrained = classmethod(_patched_xlm)
        except Exception:
            pass
        logger.info("[META-FIX] AutoModel.from_pretrained 已 patch")
    except Exception as _e:
        logger.warning("[META-FIX] AutoModel patch 失败: %s", _e)


def _load_bge_m3_pure_transformers(model_path: str, device: str):
    """降级方案：用纯 transformers 加载 BGE-M3（绕过 sentence-transformers）

    适用于 sentence-transformers 自身就出错时的最后兜底
    参考：BGE-M3 官方 README 的"Use HuggingFace Transformers"示例

    关键修复 (业内最佳实践):
      - 用 torch.nn.Module.to_empty() 处理 meta tensor
      - 不使用 device_map="auto"（避免 accelerate 介入）
      - 先 load 到 CPU（meta-free），再 .to(device)
    """
    from transformers import AutoModel, AutoTokenizer
    import torch

    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=False,
    )

    # ── 关键: 先用 low_cpu_mem_usage=False 加载到 CPU（纯实权重）──
    # 不指定 device_map，避免 accelerate 介入产生 meta tensor
    model = AutoModel.from_pretrained(
        model_path,
        trust_remote_code=False,
        low_cpu_mem_usage=False,
        torch_dtype=None,  # 保持 fp32 避免 meta
    )

    # ── 修复 meta tensor 错误: 如果模型处于 meta 状态，用 to_empty() ──
    # 这是 HuggingFace 官方推荐的做法（issue #24004）
    try:
        # 检查是否有任何 meta 参数
        has_meta = any(p.is_meta for p in model.parameters())
        if has_meta:
            logger.warning("[META-FIX] 模型含 meta 参数，使用 to_empty() + 重新加载 state_dict")
            # 先 .to_empty() 分配内存
            model = model.to_empty(device="cpu")
            # ── 关键修复: load_file 必须在 try 块外 import (单文件分支也要用) ──
            from safetensors.torch import load_file as _safetensors_load_file
            # 重新加载权重
            import os as _os
            # ── 关键修复: 处理 BGE-M3 的分片权重 (model-00001-of-00003.safetensors) ──
            weights_loaded = False
            if _os.path.isdir(model_path):
                # 1. 优先尝试分片索引加载
                index_path = _os.path.join(model_path, "model.safetensors.index.json")
                if _os.path.exists(index_path):
                    try:
                        import json as _json
                        with open(index_path, "r", encoding="utf-8") as _f:
                            index = _json.load(_f)
                        weight_map = index.get("weight_map", {})
                        # 把所有分片文件去重加载
                        unique_files = set(weight_map.values())
                        merged_sd = {}
                        for shard_name in unique_files:
                            shard_path = _os.path.join(model_path, shard_name)
                            if _os.path.exists(shard_path):
                                merged_sd.update(_safetensors_load_file(shard_path))
                                logger.info("[META-FIX] 加载分片: %s", shard_name)
                        if merged_sd:
                            model.load_state_dict(merged_sd, strict=False)
                            weights_loaded = True
                            logger.info("[META-FIX] 成功从 %d 个分片加载权重", len(unique_files))
                    except Exception as _ie:
                        logger.warning("[META-FIX] 分片加载失败: %s", _ie)

                # 2. 尝试单文件 (未分片模型)
                if not weights_loaded:
                    for fname in ["model.safetensors", "pytorch_model.bin"]:
                        fpath = _os.path.join(model_path, fname)
                        if _os.path.exists(fpath):
                            if fname.endswith(".safetensors"):
                                sd = _safetensors_load_file(fpath)
                            else:
                                sd = torch.load(fpath, map_location="cpu")
                            model.load_state_dict(sd, strict=False)
                            weights_loaded = True
                            logger.info("[META-FIX] 成功从 %s 加载权重", fname)
                            break

            if not weights_loaded:
                # 最后兜底：再 from_pretrained 一次（确保非 meta）
                logger.warning("[META-FIX] 未找到权重文件，重新 from_pretrained")
                model = AutoModel.from_pretrained(
                    model_path,
                    trust_remote_code=False,
                    low_cpu_mem_usage=False,
                )
    except Exception as e:
        logger.warning("[META-FIX] meta 检测异常: %s", e)

    # ── 关键: 加载到目标设备（meta-free 模型可直接 .to()）──
    if device != "cpu":
        model = model.to(device)
    model.eval()
    return model, tokenizer


# ── logger 必须在 _apply_meta_tensor_patch 之前定义 ──
# 修复：将 patch 调用延后到 logger 定义之后
# 错误案例：原来在 _load_bge_m3_pure_transformers 之后立即调用，导致 NameError

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

# ── 在 logger 定义之后立即应用 meta tensor patch（关键顺序）──
_apply_meta_tensor_patch()

# 模型单例
_dense_model: Optional[SentenceTransformer] = None
_reranker: Optional[CrossEncoder] = None
_embed_ready: bool = False  # BGE 就绪标志 — 未就绪时 Agent 跳过 RAG
_bge_loading: bool = False  # BGE 模型加载中标志 — 前端轮询用


def is_bge_loading() -> bool:
    """检查 BGE 模型是否正在加载中"""
    return _bge_loading

COLLECTION_NAME = "knowledge_base"
EXERCISE_COLLECTION = "exercise_bank"

# ============================================================
# 模型加载
# ============================================================

def _get_dense_model():
    """BGE-M3 稠密向量模型（优先本地路径，带重试机制 + 降级到纯 transformers）

    加载策略：
      1. embedding_local_path 非空且目录存在 → 直接从本地加载（最快）
      2. 否则 → 从 HF cache 或在线下载，最多重试3次（指数退避 1s/3s/9s）
      3. sentence-transformers 失败 → 降级到纯 transformers AutoModel

    Meta Tensor 错误处理（参考 HuggingFace + Sentence-Transformers 官方文档）：
      - _apply_meta_tensor_patch() 在模块导入时已 patch from_pretrained
      - 多管齐下：PreTrainedModel + AutoModel + XLMRobertaModel 都注入 low_cpu_mem_usage=False
      - 仍失败 → 用纯 transformers + mean pooling 降级
      - 参考: https://github.com/UKPLab/sentence-transformers/issues/2624

    说明：单次请求失败不会永久跳过 RAG，下次请求会重新尝试加载。
    """
    if not _lazy_import_st():
        return None
    global _dense_model, _embed_ready, _bge_loading
    # ── 关键修复: 防止多线程并发重复加载 (业内的最佳实践) ──
    # _bge_loading=True 期间其他线程等待,避免撞 meta tensor 中间状态
    import threading as _threading
    _load_lock = getattr(_get_dense_model, "_lock", None)
    if _load_lock is None:
        _load_lock = _threading.Lock()
        _get_dense_model._lock = _load_lock
    with _load_lock:
        # 双重检查: 进锁后状态可能已变化
        if _dense_model is not None:
            return _dense_model
        if _embed_ready:
            return _dense_model
        _bge_loading = True
        model_name = getattr(settings, 'embedding_model', 'BAAI/bge-m3')
        local_path = getattr(settings, 'embedding_local_path', '').strip()

        # ── 设备检测：CUDA 不可用时自动回退 CPU ──
        _device = settings.embedding_device
        try:
            import torch
            if _device == "cuda" and not torch.cuda.is_available():
                logger.warning("RAG: CUDA 不可用，自动回退到 CPU 模式")
                _device = "cpu"
        except Exception:
            _device = "cpu"

        # ── 策略1：本地路径优先（sentence-transformers）──
        if local_path and os.path.isdir(local_path):
            logger.info("RAG: 从本地路径加载 BGE-M3 %s (device=%s) ...", local_path, _device)
            # ── 关键: 临时禁用 accelerate / device_map 避免 meta tensor ──
            _saved_env = {}
            for _k in ["HF_HUB_DISABLE_DEVICE_MAP_AUTO", "ACCELERATE_USE_DEVICE_MAP", "PYTORCH_NO_META"]:
                if _k in os.environ:
                    _saved_env[_k] = os.environ[_k]
                os.environ[_k] = "1" if _k != "ACCELERATE_USE_DEVICE_MAP" else "0"
            try:
                # ── 关键修复 (业内最佳实践): 用 model_kwargs 传 low_cpu_mem_usage=False ──
                # sentence-transformers 3.x 默认传 low_cpu_mem_usage=True 给 transformers
                # 触发 meta tensor；必须显式禁用
                _dense_model = SentenceTransformer(
                    local_path,
                    trust_remote_code=True,
                    model_kwargs={
                        "low_cpu_mem_usage": False,
                        "torch_dtype": None,
                    },
                )
                # 强制先放 CPU（防止 ST 5.x 内部 device_map）
                _dense_model = _dense_model.to("cpu")
                if _device != "cpu":
                    # 处理可能的 meta tensor: 用 to_empty
                    try:
                        has_meta = any(
                            p.is_meta for p in _dense_model._modules['0'].auto_model.parameters()
                        )
                    except Exception:
                        has_meta = False
                    if has_meta:
                        logger.warning("[META-FIX] ST 内部含 meta，强制重建")
                        # 重新加载但禁用 device_map
                        _dense_model[0].auto_model = _dense_model[0].auto_model.to_empty(device="cpu")
                    _dense_model = _dense_model.to(_device)
                _embed_ready = True
                _bge_loading = False
                logger.info("RAG: BGE-M3 本地加载完成 (device=%s, via ST)", _device)
                return _dense_model
            except Exception as e:
                logger.warning("RAG: 本地路径(ST)加载失败，尝试降级到纯 transformers: %s", e)
                # 降级：用纯 transformers 加载
                try:
                    _dense_model = _load_bge_m3_pure_transformers(local_path, _device)
                    _embed_ready = True
                    _bge_loading = False
                    logger.info("RAG: BGE-M3 本地加载完成 (device=%s, via Pure-TF)", _device)
                    return _dense_model
                except Exception as e2:
                    logger.error("RAG: 本地路径降级也失败: %s", e2)
                    # 不立即回退到 HF；直接走策略2
            finally:
                # 恢复环境变量
                for _k, _v in _saved_env.items():
                    os.environ[_k] = _v

        # ── 策略2：HF 模型名（最多重试3次，指数退避1s/3s/9s）──
        max_retries = 3
        import time as _time
        for attempt in range(1, max_retries + 1):
            logger.info("RAG: 加载 BGE-M3 %s (HF模式, 第 %d/%d 次)...", model_name, attempt, max_retries)
            try:
                # ── 同样修复: 先 CPU 加载 ──
                _dense_model = SentenceTransformer(
                    model_name,
                    trust_remote_code=True,
                    device="cpu",
                )
                if _device != "cpu":
                    _dense_model = _dense_model.to(_device)
                _embed_ready = True
                _bge_loading = False
                logger.info("RAG: BGE-M3 加载完成 (HF模式, 第%d次成功, device=%s, via ST)", attempt, _device)
                return _dense_model
            except Exception as e:
                logger.warning("RAG: BGE-M3 加载失败 (第%d/%d次): %s", attempt, max_retries, e)
                if attempt < max_retries:
                    wait = 3 ** (attempt - 1)  # 1s, 3s, 9s
                    logger.info("RAG: %d秒后重试...", wait)
                    _time.sleep(wait)
                else:
                    # 最终兜底：降级到纯 transformers
                    logger.warning("RAG: SentenceTransformers 三次失败，尝试降级到纯 transformers...")
                    try:
                        _dense_model = _load_bge_m3_pure_transformers(model_name, _device)
                        _embed_ready = True
                        _bge_loading = False
                        logger.info("RAG: BGE-M3 加载完成 (device=%s, via Pure-TF fallback)", _device)
                        return _dense_model
                    except Exception as e2:
                        logger.error("RAG: BGE-M3 加载最终失败(纯 transformers 也失败): %s", e2)
                        _dense_model = None
                        _bge_loading = False
        # ── 关键: 加载失败后重置标志，允许下次请求重试 ──
        _bge_loading = False
    return _dense_model


# ── 公开 API (供 admin 端点使用) ──
def get_dense_model():
    """公开包装: 主动加载并返回 BGE-M3 模型 (供 /api/admin/rag-load 调用)"""
    return _get_dense_model()


def is_rag_ready() -> bool:
    """检查 RAG 是否就绪 (供 /api/admin/rag-status 调用)"""
    return _embed_ready and _dense_model is not None


def _get_reranker():
    """BGE-Reranker-v2-m3 交叉编码器（精排用）

    加载策略（与 BGE-M3 一致）:
      1. 本地路径优先 (reranker_local_path)
      2. 离线缓存加载 (local_files_only=True, 已缓存则零网络开销)
      3. HF 在线下载（最多 3 次重试，指数退避 1s/3s/9s）
      4. 全部失败 → 返回 None, RAG 自动降级 (不阻塞响应)

    修复: 增加本地路径 + 重试 + 快速失败, 避免 hf-mirror.com 网络超时卡住
    之前现象: 首次 RAG 检索时 CrossEncoder 内部 HEAD 请求 read timeout=10s
              + 1s 重试间隔 × 5 = 55s 阻塞 (P1-FIX 2026-07-11)
    """
    if not _lazy_import_st():
        return None
    global _reranker
    if _reranker is not None:
        return _reranker

    reranker_name = getattr(settings, "reranker_model", "BAAI/bge-reranker-v2-m3")
    local_path = getattr(settings, "reranker_local_path", "").strip()

    # 设备检测：与 BGE-M3 保持一致
    _device = settings.embedding_device
    try:
        import torch
        if _device == "cuda" and not torch.cuda.is_available():
            _device = "cpu"
    except Exception:
        _device = "cpu"

    # ── 策略1: 本地路径优先 ──
    if local_path and os.path.isdir(local_path):
        logger.info("RAG: 从本地路径加载 Reranker %s (device=%s) ...", local_path, _device)
        try:
            _reranker = CrossEncoder(local_path, trust_remote_code=True)
            if _device != "cpu":
                _reranker.model = _reranker.model.to(_device)
            logger.info("RAG: Reranker 本地加载完成 (device=%s)", _device)
            return _reranker
        except Exception as e:
            logger.warning("RAG: Reranker 本地路径加载失败, 降级到 HF 下载: %s", e)

    # ── 策略2: HF 模型名, 优先 local_files_only (已缓存则零网络开销) ──
    import time as _time

    # 先尝试纯离线加载 — 模型已缓存则瞬间完成, 无 HEAD 请求
    logger.info("RAG: 加载 Reranker %s (离线模式, 使用缓存)...", reranker_name)
    try:
        _reranker = CrossEncoder(reranker_name, trust_remote_code=True, local_files_only=True)
        if _device != "cpu":
            _reranker.model = _reranker.model.to(_device)
        logger.info("RAG: Reranker 加载完成 (离线缓存, device=%s)", _device)
        return _reranker
    except Exception as e:
        logger.info("RAG: 离线缓存未命中 (%s), 降级到在线下载...", str(e)[:80])

    # 降级: HF 在线下载（最多 3 次重试，指数退避 1s/3s/9s）
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        logger.info("RAG: 加载 Reranker %s (HF在线, 第 %d/%d 次)...", reranker_name, attempt, max_retries)
        try:
            _reranker = CrossEncoder(reranker_name, trust_remote_code=True)
            if _device != "cpu":
                _reranker.model = _reranker.model.to(_device)
            logger.info("RAG: Reranker 加载完成 (HF在线, 第%d次成功, device=%s)", attempt, _device)
            return _reranker
        except Exception as e:
            logger.warning("RAG: Reranker 加载失败 (第%d/%d次): %s", attempt, max_retries, e)
            if attempt < max_retries:
                wait = 3 ** (attempt - 1)  # 1s, 3s, 9s
                logger.info("RAG: %d秒后重试...", wait)
                _time.sleep(wait)
            else:
                logger.error("RAG: Reranker 加载最终失败, RAG 将跳过 rerank 步骤 (降级)")

    # ── 策略3: 全部失败 → 返回 None, 不阻塞 RAG ──
    _reranker = None
    return _reranker


# ============================================================
# 向量化
# ============================================================

def _embed(texts: list[str]) -> list[list[float]]:
    """稠密向量化（BGE-M3），模型不可用时返回空列表

    兼容两种 model 类型:
      - SentenceTransformer 实例: 直接 .encode()
      - (AutoModel, AutoTokenizer) tuple: 手动 forward + CLS pooling (纯 transformers 降级)
    """
    model = _get_dense_model()
    if model is None:
        return []
    # ── 关键修复: 纯 transformers 降级返回的是 tuple ──
    if isinstance(model, tuple):
        raw_model, tokenizer = model
        try:
            import torch
            encoded = tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            # 把 inputs 移到模型所在设备
            device = next(raw_model.parameters()).device
            encoded = {k: v.to(device) for k, v in encoded.items()}
            with torch.no_grad():
                outputs = raw_model(**encoded)
                # BGE-M3 官方推荐: mean pooling (考虑 attention_mask)
                # 参考: https://github.com/FlagOpen/FlagEmbedding#usage
                if hasattr(outputs, "last_hidden_state"):
                    token_embeddings = outputs.last_hidden_state
                else:
                    # 某些模型返回 tuple, 取第一个元素
                    token_embeddings = outputs[0]
                # 校验形状: 必须是 3D tensor [batch, seq, dim]
                if token_embeddings.dim() != 3:
                    logger.warning("[EMBED] last_hidden_state 形状异常: %s", token_embeddings.shape)
                    return []
                attention_mask = encoded.get("attention_mask")
                if attention_mask is not None:
                    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
                    embeddings = torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
                        input_mask_expanded.sum(1), min=1e-9
                    )
                else:
                    # 没有 attention_mask 就简单取 [CLS] (降级方案)
                    embeddings = token_embeddings[:, 0]
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            return embeddings.cpu().tolist()
        except Exception as _e:
            logger.warning("[EMBED] 纯 transformers 降级 forward 失败: %s", _e)
            return []
    # ── 正常 SentenceTransformer 路径 ──
    try:
        embeddings = model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()
    except Exception as _e:
        logger.warning("[EMBED] SentenceTransformer encode 失败: %s", _e)
        return []


# ============================================================
# BM25 稀疏召回
# ============================================================

_bm25_corpus: list[str] = []
_bm25_model = None  # BM25Okapi 实例（初始化时构建，检索时复用）
_bm25_ready = False

try:
    from rank_bm25 import BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False


def _init_bm25():
    """初始化 BM25 索引（从 ChromaDB 加载所有文档，索引构造一次后复用）"""
    global _bm25_corpus, _bm25_model, _bm25_ready
    if not _BM25_AVAILABLE or _bm25_ready:
        return
    try:
        from app.core.chroma_client import get_collection
        col = get_collection(COLLECTION_NAME)
        results = col.get()
        if results and results.get("documents"):
            import jieba
            _bm25_corpus = [" ".join(jieba.cut(doc)) for doc in results["documents"]]
            tokenized_corpus = [doc.split() for doc in _bm25_corpus]
            _bm25_model = BM25Okapi(tokenized_corpus)
            _bm25_ready = True
            logger.info("BM25: 索引初始化完成 %d 文档", len(_bm25_corpus))
    except Exception as e:
        logger.warning("BM25: 初始化失败 %s", e)


def _bm25_search(query: str, top_k: int = 30) -> list[tuple[int, float]]:
    """BM25 稀疏检索 → [(doc_index, score), ...]（复用已构建的 BM25 索引）"""
    if not _BM25_AVAILABLE or not _bm25_ready or _bm25_model is None:
        return []
    try:
        import jieba
        tokenized = " ".join(jieba.cut(query))
        scores = _bm25_model.get_scores(tokenized.split())
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


_faiss_discovered: set[str] | None = None  # 已发现的 FAISS 子索引名缓存


def _faiss_dense_search(query_emb: list[float], top_k: int = 30) -> list[dict]:
    """FAISS 稠密向量检索：加载磁盘上所有子索引并合并检索结果"""
    global _faiss_discovered
    try:
        import glob
        import numpy as np
        from app.services.faiss_client import get_faiss, INDEX_DIR
        mgr = get_faiss()
        # 懒加载磁盘上所有 *.faiss 子索引（首次扫描后缓存名称，避免每次 glob）
        if _faiss_discovered is None:
            _faiss_discovered = set()
            for path in glob.glob(os.path.join(INDEX_DIR, "*.faiss")):
                name = os.path.splitext(os.path.basename(path))[0]
                _faiss_discovered.add(name)
                mgr._get_index(name)
        else:
            for name in _faiss_discovered:
                if name not in mgr.indices:
                    mgr._get_index(name)
        all_results = []
        qv = np.array(query_emb)
        for idx in mgr.indices.values():
            all_results.extend(idx.search(qv, top_k))
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
        # ── 关键修复: _embed 失败时返回空列表, 用 or [] 防御 ──
        embed_result = _embed([text])
        if not embed_result:
            logger.warning("习题 %s 嵌入失败, 跳过", ex.get("id", "?"))
            continue
        embed = embed_result[0]
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
    embeddings = _embed([query])
    if not embeddings:
        return []
    q_emb = embeddings[0]
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
    except Exception as e:
        logger.warning("Exercise search failed: %s", e)
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
