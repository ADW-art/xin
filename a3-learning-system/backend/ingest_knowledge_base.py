"""
Knowledge Base Ingestion Script (Two-Phase: Embed All, Then Store)
===================================================================
Phase 1: Read all .txt files, chunk, batch-embed using BGE (no ChromaDB writes)
Phase 2: Add all embeddings to ChromaDB in one call

This avoids ChromaDB incremental indexing overhead which causes
O(n^2) slowdown with many small batch writes.

Usage:
    cd backend
    python ingest_knowledge_base.py

Required: Docker chromadb on port 8000
Required: BGE model cached locally
"""
import json
import os
import re
import sys
import time
import logging
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest")

PARSED_DIR = BACKEND_DIR / "app" / "scripts" / "knowledge_materials" / "_parsed"
EXERCISE_FILE = BACKEND_DIR / "app" / "scripts" / "knowledge_materials" / "exercise_bank.json"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
EMBED_BATCH = 128  # bigger batches = faster CPU utilization


def chunk_text(text: str, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP) -> list[str]:
    chunks = []
    if len(text) <= chunk_size:
        return [text]
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:].strip())
            break
        chunk = text[start:end]
        bp = chunk.rfind("\n\n", max(0, len(chunk) - 200))
        if bp == -1:
            bp = chunk.rfind("\n", max(0, len(chunk) - 200))
        if bp == -1:
            for sep in ["。\n", "。", ".\n", ". "]:
                bp2 = chunk.rfind(sep, max(0, len(chunk) - 200))
                if bp2 != -1:
                    bp = bp2 + len(sep)
                    break
        if bp > 0:
            end = start + bp
        chunks.append(text[start:end].strip())
        start = end - overlap if (end - overlap) > start else end
    return chunks


def clean_text(text: str) -> str:
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if re.search(r'(.)\1{4,}', stripped):
            rc = sum(1 for c in stripped if c == stripped[0])
            if rc / max(len(stripped), 1) > 0.5:
                continue
        cleaned.append(line)
    return "\n".join(cleaned)


def make_safe_id(title: str, index: int) -> str:
    safe = re.sub(r'[^a-zA-Z0-9_一-鿿-]', '_', title)
    safe = re.sub(r'_+', '_', safe).strip('_')
    return f"{safe}_{index:04d}"


def load_model():
    from app.config import settings
    from sentence_transformers import SentenceTransformer
    model_name = getattr(settings, 'embedding_model', 'BAAI/bge-m3')
    local_path = getattr(settings, 'embedding_local_path', '').strip()
    device = getattr(settings, 'embedding_device', 'cpu')
    if local_path and os.path.isdir(local_path):
        logger.info("Loading BGE from local: %s", local_path)
        return SentenceTransformer(local_path, device=device, trust_remote_code=True)
    logger.info("Loading BGE: %s (%s)", model_name, device)
    return SentenceTransformer(model_name, device=device, trust_remote_code=True)


def step1_ingest_textbooks():
    """Phase 1: Embed all textbook chunks, then add to ChromaDB in one call."""
    from app.core.chroma_client import get_collection

    txt_files = sorted(PARSED_DIR.glob("*.txt"))
    logger.info("Found %d .txt files", len(txt_files))

    # 1a: Collect all chunks
    all_chunks: list[tuple[str, str, str, str]] = []  # (id, content, title, source)
    for txt_file in txt_files:
        title = txt_file.stem
        source = str(txt_file.relative_to(BACKEND_DIR))
        try:
            raw = open(txt_file, encoding="utf-8").read()
        except Exception as e:
            logger.warning("Skip %s: %s", txt_file.name, e)
            continue
        text = clean_text(raw)
        if len(text) < 100:
            logger.warning("Skip %s: too short", txt_file.name)
            continue
        chunks = chunk_text(text)
        count = 0
        for i, ch in enumerate(chunks):
            ch = ch.strip()
            if len(ch) < 20:
                continue
            all_chunks.append((make_safe_id(title, i), ch, title, source))
            count += 1
        logger.info("  %s: %d chunks", txt_file.name, count)

    n_total = len(all_chunks)
    logger.info("Total chunks: %d", n_total)
    if n_total == 0:
        return 0

    # 1b: Embed all chunks in large batches (no ChromaDB writes yet)
    model = load_model()
    logger.info("Model loaded. Embedding %d chunks in batches of %d...", n_total, EMBED_BATCH)

    all_ids = [c[0] for c in all_chunks]
    all_texts = [c[1] for c in all_chunks]
    all_metas = [{"title": c[2], "source": c[3]} for c in all_chunks]
    all_embeddings = []

    t_embed_start = time.time()
    for i in range(0, n_total, EMBED_BATCH):
        batch_texts = all_texts[i:i + EMBED_BATCH]
        t0 = time.time()
        emb = model.encode(batch_texts, normalize_embeddings=True,
                           show_progress_bar=False, batch_size=EMBED_BATCH)
        all_embeddings.extend(emb.tolist())
        progress = min(i + EMBED_BATCH, n_total)
        logger.info("  Embed [%d/%d] %.1fs", progress, n_total, time.time() - t0)

    t_embed = time.time() - t_embed_start
    logger.info("Embedding done in %.1fs (%.2f chunks/s)", t_embed, n_total / t_embed)

    # 1c: Add ALL to ChromaDB in ONE call
    col = get_collection("knowledge_base")
    logger.info("Adding %d documents to ChromaDB in one batch...", n_total)
    t_add_start = time.time()
    col.add(documents=all_texts, metadatas=all_metas, ids=all_ids,
            embeddings=all_embeddings)
    t_add = time.time() - t_add_start
    logger.info("ChromaDB add done in %.1fs (collection: %d docs)", t_add, col.count())
    return n_total


def step2_ingest_exercises():
    """Embed all exercises, then add to ChromaDB in one call."""
    from app.core.chroma_client import get_collection

    if not EXERCISE_FILE.exists():
        logger.warning("Exercise bank not found")
        return 0

    with open(EXERCISE_FILE, encoding="utf-8") as f:
        data = json.load(f)
    exercises = data.get("exercises", [])
    logger.info("Exercise bank: %d exercises", len(exercises))

    if not exercises:
        return 0

    texts = []
    ids = []
    metas = []
    for ex in exercises:
        texts.append(f"【{ex['type']}】{ex['question']}\n答案：{ex['answer']}\n解析：{ex['explanation']}")
        ids.append(ex["id"])
        kw = ex.get("keywords", [])
        if isinstance(kw, list):
            kw = ", ".join(kw)
        metas.append({
            "type": ex["type"], "difficulty": ex["difficulty"],
            "topic": ex["topic"], "chapter": ex.get("chapter", ""),
            "keywords": kw, "source": "exercise_bank",
        })

    model = load_model()
    logger.info("Embedding %d exercises...", len(texts))
    t0 = time.time()
    embeddings = model.encode(texts, normalize_embeddings=True,
                              show_progress_bar=False, batch_size=EMBED_BATCH)
    logger.info("  Embed done in %.1fs", time.time() - t0)

    col = get_collection("exercise_bank")
    col.add(documents=texts, metadatas=metas, ids=ids, embeddings=embeddings.tolist())
    logger.info("Exercise bank stored: %d (collection count: %d)", len(texts), col.count())
    return len(texts)


def step3_build_kg():
    """Build knowledge graph from ChromaDB docs."""
    from app.services.knowledge_graph import get_graph
    from app.core.chroma_client import get_collection

    logger.info("=== Building Knowledge Graph ===")
    col = get_collection("knowledge_base")
    count = col.count()
    if count == 0:
        logger.warning("KB empty, skipping KG")
        return None

    results = col.get()
    docs = results.get("documents", [])
    metas = results.get("metadatas", [])
    logger.info("Fetched %d docs for KG", len(docs))

    books: dict[str, str] = {}
    for doc, meta in zip(docs, metas or [{}]):
        title = (meta or {}).get("title", "unknown")
        books.setdefault(title, "")
        books[title] += doc + "\n\n"
    logger.info("%d books for extraction", len(books))

    kg = get_graph()
    kg.build_from_texts([{"title": t, "content": c} for t, c in books.items()])
    logger.info("KG: %d nodes, %d edges", len(kg.nodes),
                sum(len(e) for e in kg.edges.values()))

    phases = kg.topological_sort()
    logger.info("Learning phases: %d", len(phases))
    for i, p in enumerate(phases[:5]):
        logger.info("  Phase %d: %s", i + 1, ", ".join(p[:5]))

    time_est = kg.estimate_time(phases, weekly_hours=10.0)
    logger.info("Est: %.1fh / %d weeks @ 10h/week",
                sum(x["estimated_hours"] for x in time_est),
                sum(x["estimated_weeks"] for x in time_est))
    return kg


def step4_verify():
    """Verify ingestion results."""
    from app.core.chroma_client import get_collection

    logger.info("=== Verification ===")
    model = load_model()

    for cname in ["knowledge_base", "exercise_bank"]:
        col = get_collection(cname)
        logger.info("  %s: %d docs", cname, col.count())

    kb = get_collection("knowledge_base")
    if kb.count() > 0:
        queries = ["Python列表", "排序算法", "数据结构", "递归函数"]
        for q in queries:
            emb = model.encode([q], normalize_embeddings=True)
            try:
                r = kb.query(query_embeddings=emb.tolist(), n_results=3)
                srcs = [m.get("title","?") for m in r["metadatas"][0]]
                scs = [f"{1-d:.3f}" for d in r["distances"][0]]
                logger.info("  '%s' -> %s (scores: %s)", q, srcs, scs)
            except Exception as e:
                logger.warning("  '%s': %s", q, e)


def main():
    logger.info("=" * 50)
    logger.info("A3 Knowledge Base Ingestion (Two-Phase)")
    logger.info("=" * 50)
    t0 = time.time()

    logger.info("\n[1/4] Textbooks (embed all -> store all)...")
    n1 = step1_ingest_textbooks()

    logger.info("\n[2/4] Exercise bank...")
    n2 = step2_ingest_exercises()

    logger.info("\n[3/4] Knowledge Graph...")
    step3_build_kg()

    logger.info("\n[4/4] Verify...")
    step4_verify()

    logger.info("\n=== Done in %.1fs | KB: %d | EX: %d ===", time.time() - t0, n1, n2)


if __name__ == "__main__":
    main()
