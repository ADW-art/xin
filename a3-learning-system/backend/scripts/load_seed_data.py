"""
种子数据加载脚本
================

首次启动应用时自动从仓库内的 seed_data/ 加载 Python 示例知识到 ChromaDB。
新人 clone 项目后无需任何操作，知识库自动有数据可用。

加载策略：
- 检查知识库是否为空 → 空则加载种子，非空则跳过
- 强制模式（--force）：清空后重新加载
- 失败不阻断主应用启动（仅 warning）

作者: A3 Learning System 维护者
"""

import json
import gzip
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 路径：backend/scripts/load_seed_data.py → backend/seed_data/
SEED_DIR = Path(__file__).parent.parent / "seed_data"


def _load_one_jsonl_gz(file_path: Path) -> list:
    """读取 .jsonl.gz 文件，返回 records 列表"""
    records = []
    with gzip.open(file_path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def load_seed_data(force: bool = False) -> dict:
    """
    加载种子数据到 ChromaDB。

    Args:
        force: 是否强制重载（清空后重新加载）

    Returns:
        dict: {"knowledge_base": N, "exercise_bank": M, "skipped": bool}
    """
    # 延迟导入（避免启动时强制依赖 chromadb）
    try:
        import chromadb
        from app.core.config import settings
    except ImportError as e:
        logger.warning(f"[seed] 跳过种子加载 (导入失败: {e})")
        return {"knowledge_base": 0, "exercise_bank": 0, "skipped": True}

    if not SEED_DIR.exists():
        logger.info(f"[seed] 种子目录不存在 {SEED_DIR}, 跳过")
        return {"knowledge_base": 0, "exercise_bank": 0, "skipped": True}

    # 解析持久化目录（和 rag_service 保持一致）
    persist_dir = settings.chroma_persist_dir
    if not Path(persist_dir).is_absolute():
        # 相对路径基于 backend/
        persist_dir = Path(__file__).parent.parent / persist_dir

    try:
        client = chromadb.PersistentClient(path=str(persist_dir))
    except Exception as e:
        logger.warning(f"[seed] ChromaDB 客户端初始化失败: {e}, 跳过")
        return {"knowledge_base": 0, "exercise_bank": 0, "skipped": True}

    result = {"knowledge_base": 0, "exercise_bank": 0, "skipped": False}

    # === 1. knowledge_base ===
    kb_seed = SEED_DIR / "python_kb.jsonl.gz"
    if kb_seed.exists():
        try:
            col = client.get_or_create_collection("knowledge_base")

            if col.count() > 0 and not force:
                logger.info(f"[seed] knowledge_base 已有 {col.count()} 条, 跳过种子加载")
                result["skipped"] = True
            else:
                if force and col.count() > 0:
                    logger.warning(f"[seed] 强制重载, 先清空 {col.count()} 条旧数据")
                    # 获取所有 ID 然后删除
                    all_ids = col.get(include=[])["ids"]
                    if all_ids:
                        col.delete(ids=all_ids)

                logger.info(f"[seed] 正在加载 Python 知识种子: {kb_seed.name}")
                records = _load_one_jsonl_gz(kb_seed)
                logger.info(f"[seed] 种子文件包含 {len(records)} 条记录")

                # 批量写入（ChromaDB 一次最多 ~41k 条）
                BATCH = 41666
                for i in range(0, len(records), BATCH):
                    batch = records[i:i + BATCH]
                    col.add(
                        ids=[r["id"] for r in batch],
                        documents=[r["content"] for r in batch],
                        embeddings=[r["embedding"] for r in batch if r["embedding"]],
                        metadatas=[r["metadata"] for r in batch],
                    )
                    logger.info(f"[seed] knowledge_base 进度: {min(i + BATCH, len(records))}/{len(records)}")

                result["knowledge_base"] = len(records)
                logger.info(f"✅ [seed] knowledge_base 加载完成: {len(records)} 条 Python 知识")

        except Exception as e:
            logger.error(f"[seed] knowledge_base 加载失败: {e}")

    # === 2. exercise_bank ===
    ex_seed = SEED_DIR / "python_exercises.jsonl.gz"
    if ex_seed.exists():
        try:
            col = client.get_or_create_collection("exercise_bank")

            if col.count() > 0 and not force:
                logger.info(f"[seed] exercise_bank 已有 {col.count()} 条, 跳过")
            else:
                if force and col.count() > 0:
                    all_ids = col.get(include=[])["ids"]
                    if all_ids:
                        col.delete(ids=all_ids)

                logger.info(f"[seed] 正在加载 Python 习题种子: {ex_seed.name}")
                records = _load_one_jsonl_gz(ex_seed)
                col.add(
                    ids=[r["id"] for r in records],
                    documents=[r["content"] for r in records],
                    embeddings=[r["embedding"] for r in records if r["embedding"]],
                    metadatas=[r["metadata"] for r in records],
                )
                result["exercise_bank"] = len(records)
                logger.info(f"✅ [seed] exercise_bank 加载完成: {len(records)} 条 Python 习题")

        except Exception as e:
            logger.error(f"[seed] exercise_bank 加载失败: {e}")

    return result


if __name__ == "__main__":
    # 允许命令行手动调用
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    force = "--force" in sys.argv
    if force:
        print("⚠️  强制重载模式: 将清空已有数据")

    result = load_seed_data(force=force)
    print(f"\n📊 加载结果: {result}")
