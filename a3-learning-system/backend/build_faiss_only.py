"""
只构建 FAISS 子索引（复用 rebuild_stores 的逻辑），完全不碰 ChromaDB。
可在后端运行时安全执行：只读 _rebuild_source.jsonl + _emb.f32，只写 faiss_indices/。
"""
from rebuild_stores import load_source, load_emb, rebuild_faiss

ids, docs, metas = load_source()
sources = [m.get("source", "") for m in metas]
emb = load_emb(len(ids))
print(f"loaded {len(ids)} docs, emb {emb.shape}", flush=True)
rebuild_faiss(docs, metas, emb, sources)
print("FAISS_ONLY_DONE", flush=True)
