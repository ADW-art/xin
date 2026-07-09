"""
重嵌入脚本（可断点续跑）

读取 _rebuild_source.jsonl 的 39005 块文本，用真实 BGE 模型编码成归一化向量，
按行追加写入 _emb.f32（float32, 每行 dim 个）。进程被杀后可重跑，自动从已编码行数续跑。

用法：
  python reembed.py                      # 默认 BAAI/bge-m3
  python reembed.py BAAI/bge-large-zh-v1.5
"""
import os, sys, json, time, struct

# 稳定性：模型已缓存 → 强制离线，避免 hf-mirror HEAD 超时
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
# 关键：隐藏不被 torch 2.5.1 支持的 RTX 5060(sm_120)，避免 CUDA 上下文导致 CPU 推理段错误
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
# 限制原生线程，降低 MKL/OpenMP 竞争导致的崩溃
os.environ["OMP_NUM_THREADS"] = "16"
os.environ["MKL_NUM_THREADS"] = "16"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

MODEL = sys.argv[1] if len(sys.argv) > 1 else "BAAI/bge-m3"
SRC = "_rebuild_source.jsonl"
EMB = "_emb.f32"
DIM = 1024
BATCH = 32

def load_docs():
    docs = []
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            docs.append(json.loads(line)["doc"])
    return docs

def encoded_rows():
    if not os.path.exists(EMB):
        return 0
    return os.path.getsize(EMB) // (DIM * 4)

def main():
    docs = load_docs()
    total = len(docs)
    done = encoded_rows()
    print(f"model={MODEL} total={total} already_encoded={done}", flush=True)
    if done >= total:
        print("ALL_DONE", flush=True)
        return

    import torch
    torch.set_num_threads(16)
    from sentence_transformers import SentenceTransformer
    t0 = time.time()
    model = SentenceTransformer(MODEL, device="cpu")
    print(f"model loaded in {time.time()-t0:.0f}s", flush=True)

    f = open(EMB, "ab")
    t1 = time.time()
    i = done
    while i < total:
        batch = docs[i:i + BATCH]
        vecs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        for v in vecs:
            f.write(struct.pack(f"{DIM}f", *[float(x) for x in v]))
        f.flush()
        os.fsync(f.fileno())
        i += len(batch)
        if i % 640 == 0 or i >= total:
            rate = (i - done) / max(time.time() - t1, 1)
            eta = (total - i) / max(rate, 0.001) / 60
            print(f"  {i}/{total}  {rate:.1f} chunk/s  ETA {eta:.0f}min", flush=True)
    f.close()
    print("ENCODE_COMPLETE", flush=True)

if __name__ == "__main__":
    main()
