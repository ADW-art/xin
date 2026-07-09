"""
Embedding 模型预下载脚本

功能：
  1. 下载 BGE-M3 到本地指定目录（离线部署用）
  2. 下载 BGE-Reranker-v2-m3
  3. 验证模型完整性
  4. 输出配置建议（embedding_local_path）

使用方式：
  # 下载到默认位置（backend/models/）
  python -m app.scripts.preload_models

  # 下载到自定义目录
  python -m app.scripts.preload_models --output-dir ./my_models

  # 仅检查已有模型
  python -m app.scripts.preload_models --check-only

环境变量：
  HF_ENDPOINT   - HF 镜像站地址（默认 https://hf-mirror.com）
"""

import argparse
import logging
import os
import sys
import time

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 模型列表
MODELS = [
    {
        "name": "BAAI/bge-m3",
        "desc": "BGE-M3 稠密向量模型（多语言、多函数）",
        "subdir": "bge-m3",
    },
    {
        "name": "BAAI/bge-reranker-v2-m3",
        "desc": "BGE-Reranker-v2-m3 交叉编码器精排模型",
        "subdir": "bge-reranker-v2-m3",
    },
]


def download_model(model_name: str, output_dir: str, check_only: bool = False) -> bool:
    """下载/检询单个模型

    Args:
        model_name: HuggingFace 模型名
        output_dir: 本地保存目录
        check_only: 仅检查是否已存在

    Returns:
        True 成功/已存在, False 失败
    """
    target_path = os.path.join(output_dir, model_name.replace("/", "_"))

    if os.path.isdir(target_path):
        required_files = ["config.json", "model.safetensors"]
        # 也检查 pytorch_model.bin 或 model.safetensors.index.json (sharded)
        has_config = os.path.isfile(os.path.join(target_path, "config.json"))
        has_weights = (
            os.path.isfile(os.path.join(target_path, "model.safetensors"))
            or os.path.isfile(os.path.join(target_path, "pytorch_model.bin"))
            or os.path.isfile(os.path.join(target_path, "model.safetensors.index.json"))
        )

        if has_config and has_weights:
            logger.info("✅ %s → 已存在于 %s", model_name, target_path)
            return True
        else:
            logger.warning("⚠️ %s → 目录存在但文件不完整，重新下载", model_name)

    if check_only:
        logger.error("❌ %s → 未找到，需要下载", model_name)
        return False

    logger.info("📥 正在下载 %s → %s ...", model_name, target_path)
    start = time.time()

    try:
        from sentence_transformers import SentenceTransformer

        # 先下载（sentence_transformers 会缓存到 ~/.cache/huggingface/）
        model = SentenceTransformer(model_name, trust_remote_code=True)

        # 再复制到目标目录
        model.save(target_path)

        elapsed = time.time() - start
        logger.info("✅ %s → 下载完成 (%.1fs) → %s", model_name, elapsed, target_path)

        # 清理 GPU 显存（如果有）
        import gc
        del model
        gc.collect()

        return True

    except Exception as e:
        logger.error("❌ %s → 下载失败: %s", model_name, e)
        return False


def download_reranker(model_name: str, output_dir: str, check_only: bool = False) -> bool:
    """下载 CrossEncoder 类型的 Reranker 模型"""
    target_path = os.path.join(output_dir, model_name.replace("/", "_"))

    if os.path.isdir(target_path):
        if os.path.isfile(os.path.join(target_path, "config.json")):
            logger.info("✅ %s → 已存在于 %s", model_name, target_path)
            return True
        else:
            logger.warning("⚠️ %s → 目录存在但文件不完整，重新下载", model_name)

    if check_only:
        logger.error("❌ %s → 未找到，需要下载", model_name)
        return False

    logger.info("📥 正在下载 %s → %s ...", model_name, target_path)
    start = time.time()

    try:
        from sentence_transformers import CrossEncoder

        model = CrossEncoder(model_name, trust_remote_code=True)
        model.save(target_path)

        elapsed = time.time() - start
        logger.info("✅ %s → 下载完成 (%.1fs) → %s", model_name, elapsed, target_path)

        import gc
        del model
        gc.collect()

        return True

    except Exception as e:
        logger.error("❌ %s → 下载失败: %s", model_name, e)
        return False


def main():
    parser = argparse.ArgumentParser(description="预下载 Embedding 模型到本地")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "..", "..", "models"),
        help="模型保存目录（默认: backend/models/）",
    )
    parser.add_argument("--check-only", action="store_true", help="仅检查是否已下载")
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    logger.info("=" * 60)
    logger.info("Embedding 模型预下载工具")
    logger.info("输出目录: %s", output_dir)
    logger.info("=" * 60)

    # 设置 HF 镜像
    hf_endpoint = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ["HF_ENDPOINT"] = hf_endpoint
    logger.info("HF Endpoint: %s", hf_endpoint)

    results = {}

    # 1. BGE-M3
    results["bge_m3"] = download_model(
        MODELS[0]["name"], output_dir, check_only=args.check_only
    )

    # 2. Reranker
    results["reranker"] = download_reranker(
        MODELS[1]["name"], output_dir, check_only=args.check_only
    )

    # ── 结果汇总 ──
    logger.info("=" * 60)
    logger.info("结果汇总:")
    all_ok = True
    for name, ok in results.items():
        status = "✅ 成功" if ok else "❌ 失败"
        logger.info("  %s: %s", name, status)
        if not ok:
            all_ok = False

    if all_ok and not args.check_only:
        logger.info("")
        logger.info("🎉 全部下载完成！")
        logger.info("")
        logger.info("请在 .env 中添加以下配置启用本地模型：")
        logger.info("  EMBEDDING_LOCAL_PATH=%s", os.path.join(output_dir, MODELS[0]["name"].replace("/", "_")))
        logger.info("")
        logger.info("或在 config.py 中修改 embedding_local_path")

    elif not all_ok:
        logger.error("")
        logger.error("部分模型下载失败，请检查网络或代理设置后重试。")
        sys.exit(1)


if __name__ == "__main__":
    main()
