"""
用 BGE 重新计算 Python 相关记录的 embedding 并导出种子
========================================================

主人本地 ChromaDB 里的 Python 关键词记录大部分没有 embedding（异常状态），
直接导出会有大量"无 embedding"的记录，无法被新用户加载使用。

这个脚本：
1. 从 ChromaDB 读取所有 Python 相关的 (id, content, metadata)
2. 用 BGE-M3 重新计算 embedding
3. 写出 .jsonl.gz 种子
4. 可选: 写回原 ChromaDB collection 修复主人自己的数据

耗时: ~2-5 分钟 (1371+51 条 Python 关键词 × BGE)
"""

import os
import sys
import json
import gzip
import logging
from pathlib import Path
from datetime import datetime

os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_DISABLED"] = "True"
os.environ["HF_HUB_OFFLINE"] = "1"  # 使用本地缓存的 BGE

import chromadb
import numpy as np

# 路径
BACKEND_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BACKEND_DIR / "chroma_data_local"
SEED_DIR = BACKEND_DIR / "seed_data"
SEED_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reembed_export")


def is_python_related(meta: dict) -> bool:
    """同 export_python_seed.py 的逻辑"""
    title = (meta.get("title") or "").lower()
    source = (meta.get("source") or "").lower()
    if "curated_knowledge_bank" in source:
        py_keywords = [
            "python", "py基础", "py_", "变量", "函数", "循环", "类", "对象",
            "列表", "字典", "元组", "字符串", "模块", "包", "异常", "文件",
            "装饰器", "生成器", "迭代器", "推导式", "lambda", "面向对象",
            "py", "安装", "环境", "pip", "conda", "venv", "pycharm", "jupyter"
        ]
        for kw in py_keywords:
            if kw in title:
                return True
        return False
    py_title_keywords = ["python", "py"]
    for kw in py_title_keywords:
        if kw in title:
            return True
    return False


def main(write_back: bool = False):
    print("=" * 60)
    print("🐾 BGE 重算 + 导出 Python 种子 (v3)")
    print("=" * 60)

    if not CHROMA_DIR.exists():
        print(f"❌ ChromaDB 目录不存在: {CHROMA_DIR}")
        sys.exit(1)

    # === 1. 加载 BGE 模型 ===
    print("\n[1/4] 加载 BGE-M3 模型...")
    sys.path.insert(0, str(BACKEND_DIR))
    from app.services.rag_service import _embed
    # 用一个空文本触发模型加载
    _ = _embed([""])
    print("  ✅ BGE 已就绪")

    # === 2. 读出所有 Python 相关记录 (id, content, metadata) ===
    print("\n[2/4] 读出所有 Python 相关记录...")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = client.get_collection("knowledge_base")
    total = col.count()
    print(f"  knowledge_base 总记录: {total}")

    python_records = []  # [{"id", "content", "metadata"}, ...]
    BATCH = 1000
    for offset in range(0, total, BATCH):
        try:
            batch = col.get(limit=BATCH, offset=offset, include=["documents", "metadatas"])
        except Exception as e:
            print(f"  ⚠️  offset={offset} 读取失败: {e}, 跳过")
            continue

        for i, doc_id in enumerate(batch["ids"]):
            meta = batch["metadatas"][i] if batch.get("metadatas") and i < len(batch["metadatas"]) else {}
            if is_python_related(meta):
                python_records.append({
                    "id": doc_id,
                    "content": batch["documents"][i] if batch.get("documents") and i < len(batch["documents"]) else "",
                    "metadata": meta,
                })
        if (offset // BATCH) % 5 == 0:
            print(f"  读进度: {min(offset+BATCH, total)}/{total}, 已筛 {len(python_records)} 条")

    print(f"  ✅ 共筛出 {len(python_records)} 条 Python 相关记录")

    if not python_records:
        print("  ❌ 没筛出任何记录, 退出")
        return

    # === 3. 用 BGE 计算 embedding (分批) ===
    print("\n[3/4] 用 BGE-M3 重新计算 embedding...")
    EMB_BATCH = 8  # 减小批次防止 OOM
    all_embeddings = [None] * len(python_records)

    # 用临时文件每 25% 增量写入, 防止终端被 kill
    output_file = SEED_DIR / "python_seed.jsonl.gz"
    temp_file = SEED_DIR / "_partial.jsonl.gz"

    # 读取已有进度
    start_idx = 0
    partial_records = []
    if temp_file.exists():
        try:
            with gzip.open(temp_file, "rt", encoding="utf-8") as f:
                for line in f:
                    partial_records.append(json.loads(line))
            start_idx = len(partial_records)
            print(f"  ⚡ 恢复进度: 已算 {start_idx} 条")
        except Exception:
            partial_records = []
            start_idx = 0

    for i in range(start_idx, len(python_records), EMB_BATCH):
        batch_records = python_records[i:i+EMB_BATCH]
        texts = [r["content"][:4096] for r in batch_records]  # 截断到 4k 字符
        try:
            embs = _embed(texts)
            for j, e in enumerate(embs):
                if e is not None and len(e) == 1024:
                    all_embeddings[i + j] = e
        except Exception as e:
            print(f"  ⚠️  BGE 失败 offset={i}: {e}, 跳过这批")

        # 每 4 批 (~32 条) 增量写入
        if (i - start_idx) // EMB_BATCH % 4 == 3 or i + EMB_BATCH >= len(python_records):
            with gzip.open(temp_file, "at", encoding="utf-8") as f:
                for j in range(min(EMB_BATCH, len(python_records) - i)):
                    if all_embeddings[i + j] is not None:
                        r = python_records[i + j]
                        rec = {
                            "id": r["id"],
                            "content": r["content"],
                            "embedding": [float(x) for x in all_embeddings[i + j]],
                            "metadata": r["metadata"],
                        }
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            pct = min(100, (i + EMB_BATCH) * 100 // len(python_records))
            print(f"  BGE 进度: {pct}% ({min(i+EMB_BATCH, len(python_records))}/{len(python_records)})", flush=True)

    # === 4. 合并到最终文件 ===
    print("\n[4/4] 合并到最终种子文件...")
    final_file = output_file
    if final_file.exists():
        final_file.unlink()
    temp_file.rename(final_file)

    size_mb = final_file.stat().st_size / 1024 / 1024
    print(f"  📦 写入: {final_file.name} ({size_mb:.2f} MB)")

    # 统计有效数
    valid_count = sum(1 for e in all_embeddings if e is not None)
    print(f"  ✅ 有效 embedding: {valid_count} / {len(python_records)}")

    # VERSION
    version_info = {
        "generated_at": datetime.now().isoformat(),
        "total_records": len(valid_records),
        "chroma_version": chromadb.__version__,
        "bge_model": "BAAI/bge-m3 (re-computed)",
        "embedding_dim": 1024,
        "purpose": "Python 学习系统种子数据 (BGE 重算, 开箱即用)",
        "regen_command": "python backend/scripts/reembed_and_export.py",
        "min_chroma_version": "0.5.0",
        "min_bge_model": "BAAI/bge-m3",
    }
    with open(SEED_DIR / "VERSION.json", "w", encoding="utf-8") as f:
        json.dump(version_info, f, ensure_ascii=False, indent=2)

    # === 5. 可选: 写回原 ChromaDB ===
    if write_back:
        print("\n[5/5] 写回原 ChromaDB (修复主人本地数据)...")
        BATCH = 41666
        for i in range(0, len(valid_records), BATCH):
            batch_r = valid_records[i:i+BATCH]
            batch_e = valid_embeddings[i:i+BATCH]
            try:
                col.update(
                    ids=[r["id"] for r in batch_r],
                    embeddings=batch_e,
                    documents=[r["content"] for r in batch_r],
                    metadatas=[r["metadata"] for r in batch_r],
                )
                print(f"  写回进度: {min(i+BATCH, len(valid_records))}/{len(valid_records)}")
            except Exception as e:
                print(f"  ⚠️  写回失败: {e}")

    print("\n" + "=" * 60)
    print(f"✅ 完成! 共 {len(valid_records)} 条有效种子")
    print("=" * 60)


if __name__ == "__main__":
    write_back = "--write-back" in sys.argv
    if write_back:
        print("⚠️  模式: 写回原 ChromaDB (会更新主人本地数据)")
    main(write_back=write_back)
