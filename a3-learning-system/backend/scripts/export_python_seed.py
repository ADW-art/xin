"""
Python 知识库种子数据导出（简化可靠版）
========================================

输出: backend/seed_data/python_seed.jsonl.gz
包含: Python 关键词记录 + 51 个治理概念（真正的 Python 课程）
"""

import json
import gzip
import os
import sys
from pathlib import Path
from datetime import datetime

os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_DISABLED"] = "True"

import chromadb

# 路径
BACKEND_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BACKEND_DIR / "chroma_data_local"
SEED_DIR = BACKEND_DIR / "seed_data"
SEED_DIR.mkdir(parents=True, exist_ok=True)


def is_python_related(meta: dict) -> bool:
    """判断一条记录是否和 Python 相关"""
    title = (meta.get("title") or "").lower()
    source = (meta.get("source") or "").lower()

    # 1. 治理概念：source 标记为 curated_knowledge_bank 的就是课程级内容
    if "curated_knowledge_bank" in source:
        # 再看 title 是否是 Python 相关（避免把 Java/C++ 的概念混入）
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

    # 2. PDF 教材类：title 含 python 关键词
    py_title_keywords = ["python", "py"]
    for kw in py_title_keywords:
        if kw in title:
            return True

    return False


def main():
    print("=" * 60)
    print("🐾 Python 知识库种子导出 (v2)")
    print("=" * 60)

    if not CHROMA_DIR.exists():
        print(f"❌ ChromaDB 目录不存在: {CHROMA_DIR}")
        sys.exit(1)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = client.get_collection("knowledge_base")
    total = col.count()
    print(f"knowledge_base 总记录: {total}")

    # 流式写：一边读一边写，不在内存堆全部
    BATCH = 1000
    output_file = SEED_DIR / "python_seed.jsonl.gz"
    skipped_non_python = 0
    skipped_no_embedding = 0
    exported = 0

    with gzip.open(output_file, "wt", encoding="utf-8") as f:
        for offset in range(0, total, BATCH):
            try:
                batch = col.get(
                    limit=BATCH,
                    offset=offset,
                    include=["documents", "metadatas", "embeddings"]
                )
            except Exception as e:
                print(f"  ⚠️  offset={offset} 读取失败: {e}, 跳过此批")
                continue

            ids = batch["ids"]
            documents = batch.get("documents") or []
            metadatas = batch.get("metadatas") or []
            embeddings = batch.get("embeddings")
            if embeddings is None:
                embeddings = []

            for i, doc_id in enumerate(ids):
                meta = metadatas[i] if i < len(metadatas) else {}
                if not is_python_related(meta):
                    skipped_non_python += 1
                    continue

                # 关键：必须 embedding 存在且有效, 否则跳过
                # (ChromaDB add() 要求 ids/embeddings 长度一致)
                if i >= len(embeddings) or embeddings[i] is None:
                    skipped_no_embedding += 1
                    continue

                # 转为 list[float]
                try:
                    emb_list = [float(x) for x in embeddings[i]]
                except (TypeError, ValueError):
                    skipped_no_embedding += 1
                    continue

                # 验证维度 (BGE-M3 = 1024)
                if len(emb_list) != 1024:
                    skipped_no_embedding += 1
                    continue

                record = {
                    "id": doc_id,
                    "content": documents[i] if i < len(documents) else "",
                    "embedding": emb_list,
                    "metadata": meta,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                exported += 1

            if (offset // BATCH) % 10 == 0:
                print(f"  进度: {min(offset + BATCH, total)}/{total} (已导出 {exported}, 跳非Python {skipped_non_python}, 跳无emb {skipped_no_embedding})")
                f.flush()  # 强制刷新磁盘

    print(f"\n✅ 筛选完成: {exported} 条 Python 记录")
    print(f"   跳过非Python: {skipped_non_python}, 跳过无embedding: {skipped_no_embedding}")

    size_mb = output_file.stat().st_size / 1024 / 1024
    print(f"📦 写入: {output_file.name} ({size_mb:.2f} MB)")

    # 写 VERSION
    version_info = {
        "generated_at": datetime.now().isoformat(),
        "total_records": exported,
        "chroma_version": chromadb.__version__,
        "bge_model": "BAAI/bge-m3",
        "embedding_dim": 1024,
        "purpose": "Python 学习系统种子数据, 包含 51 个治理概念 + PDF 教材提及",
        "regen_command": "python backend/scripts/export_python_seed.py",
        "min_chroma_version": "0.5.0",
        "min_bge_model": "BAAI/bge-m3",
    }
    version_file = SEED_DIR / "VERSION.json"
    with open(version_file, "w", encoding="utf-8") as f:
        json.dump(version_info, f, ensure_ascii=False, indent=2)
    print(f"📝 版本信息: {version_file.name}")

    print(f"\n📁 种子目录: {SEED_DIR}")
    print(f"📊 总大小: {size_mb:.2f} MB")
    print("\n下一步:")
    print("  1. git add backend/seed_data/")
    print("  2. git add backend/scripts/load_seed_data.py")
    print("  3. git commit -m 'feat(seed): add Python 知识种子 (开箱即用)'")


if __name__ == "__main__":
    main()
