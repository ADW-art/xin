"""
重建向量库：用 _rebuild_source.jsonl(文本) + _emb.f32(真实向量) 重建
干净的 ChromaDB knowledge_base 集合（修掉零向量+HNSW损坏），并填充 FAISS。

前置：reembed.py 已生成 _emb.f32 且行数 == jsonl 行数。
用法：python rebuild_stores.py
"""
import os, json, struct, logging
logging.disable(logging.CRITICAL)
import numpy as np

SRC = "_rebuild_source.jsonl"
EMB = "_emb.f32"
DIM = 1024
COLL = "knowledge_base"

# ascii 文件夹前缀 → FAISS 子索引（route 用，避免乱码中文匹配失败）
PREFIX_MAP = {
    "linux": "os", "computer-system": "os", "os": "os",
    "algorithms": "datastructure", "algorithm": "datastructure",
    "mysql": "database", "mongodb": "database", "database": "database",
    "c": "clang", "c++": "clang", "cpp": "clang",
    "java": "java",
    "ai_ml": "ai_ml", "ai": "ai_ml",
}

def route(source: str) -> str:
    pre = (source.split("/", 1)[0] if "/" in source else source).strip().lower()
    return PREFIX_MAP.get(pre, "default")

def load_source():
    ids, docs, metas = [], [], []
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            ids.append(r["id"]); docs.append(r["doc"]); metas.append(r.get("meta") or {})
    return ids, docs, metas

def load_emb(n):
    raw = np.fromfile(EMB, dtype=np.float32)
    rows = raw.size // DIM
    arr = raw[: rows * DIM].reshape(rows, DIM)
    assert rows == n, f"emb rows {rows} != docs {n} — reembed 未完成"
    return arr

def rebuild_chroma(ids, docs, metas, emb):
    import chromadb
    from chromadb.config import Settings
    c = chromadb.PersistentClient(path=os.path.abspath("chroma_data_local"),
                                  settings=Settings(anonymized_telemetry=False))
    try:
        c.delete_collection(COLL)
        print("dropped old", COLL, flush=True)
    except Exception as e:
        print("drop skip:", str(e)[:60], flush=True)
    col = c.create_collection(COLL, metadata={"hnsw:space": "cosine"})
    B = 256
    added = 0
    for i in range(0, len(ids), B):
        sl = slice(i, i + B)
        try:
            col.add(documents=docs[sl], embeddings=emb[sl].tolist(),
                    metadatas=metas[sl], ids=ids[sl])
            added += len(ids[sl])
        except Exception:
            for j in range(i, min(i + B, len(ids))):
                try:
                    col.add(documents=[docs[j]], embeddings=[emb[j].tolist()],
                            metadatas=[metas[j]], ids=[ids[j]]); added += 1
                except Exception:
                    pass
        if (i // B) % 20 == 0:
            print(f"  chroma {added}/{len(ids)}", flush=True)
    print(f"CHROMA_DONE count={col.count()}", flush=True)
    return col.count()

def rebuild_faiss(docs, metas, emb, sources):
    import sys
    sys.path.insert(0, os.path.abspath("."))
    from app.services.faiss_client import get_faiss
    # 清空旧索引文件
    idir = os.path.abspath("faiss_indices")
    if os.path.isdir(idir):
        for fn in os.listdir(idir):
            os.remove(os.path.join(idir, fn))
    mgr = get_faiss(DIM)
    buckets: dict[str, list[int]] = {}
    for k, s in enumerate(sources):
        buckets.setdefault(route(s), []).append(k)
    for name, idxs in buckets.items():
        vecs = emb[idxs].tolist()
        txts = [docs[k] for k in idxs]
        mts = [metas[k] for k in idxs]
        mgr.upsert(name, vecs, txts, mts)
    mgr.save_all()
    dist = {n: len(v) for n, v in buckets.items()}
    print(f"FAISS_DONE total={mgr.get_total()} dist={dist}", flush=True)

def main():
    ids, docs, metas = load_source()
    sources = [m.get("source", "") for m in metas]
    emb = load_emb(len(ids))
    norms = np.linalg.norm(emb[:100], axis=1)
    print(f"loaded {len(ids)} docs, emb shape {emb.shape}, sample norm {norms.mean():.3f}", flush=True)
    rebuild_chroma(ids, docs, metas, emb)
    rebuild_faiss(docs, metas, emb, sources)
    print("ALL_REBUILT", flush=True)

if __name__ == "__main__":
    main()
