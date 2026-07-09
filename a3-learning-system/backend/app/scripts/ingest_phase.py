"""
Phase 2: 嵌入入库 — 读取 _full_scan_texts/*.txt → 分块 → 批量嵌入 → ChromaDB
支持断点续传，进度存 ingest_phase_progress.json

用法:
  python -m app.scripts.ingest_phase           # 全部
  python -m app.scripts.ingest_phase --batch 32  # 大批次
"""
import io, sys, os, time, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.rag_service import _embed, ingest_document, get_knowledge_count

TEXT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '_full_scan_texts')
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'ingest_phase_progress.json')

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS = 500  # 全量书允许更多chunks
BATCH_SIZE = 24


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_progress(prog):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)


def chunk_text(text, max_chunks=MAX_CHUNKS):
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < max_chunks:
        end = start + CHUNK_SIZE
        c = text[start:end].strip()
        if c and len(c) > 30:
            chunks.append(c)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def process_book(title, txt_path, progress):
    book_prog = progress.get(title, {"ingested": 0, "total_chunks": 0})
    if book_prog.get("status") == "done":
        return True

    with open(txt_path, 'r', encoding='utf-8') as f:
        text = f.read()

    chunks = chunk_text(text)
    book_prog["total_chunks"] = len(chunks)
    book_prog["total_chars"] = len(text)
    start = book_prog.get("ingested", 0)
    new_chunks = chunks[start:]

    if not new_chunks:
        book_prog["status"] = "done"
        progress[title] = book_prog
        save_progress(progress)
        return True

    total = len(chunks)
    t0 = time.time()
    ok = 0

    for batch_start in range(0, len(new_chunks), BATCH_SIZE):
        batch = new_chunks[batch_start:batch_start + BATCH_SIZE]
        try:
            embs = _embed(batch)
            for j, emb in enumerate(embs):
                i = start + batch_start + j
                doc_id = f"materials:full:{title}:chunk{i}"
                try:
                    ingest_document(content=batch[j], title=title,
                                   source=f"materials/full/{title}",
                                   doc_id=doc_id)
                    ok += 1
                except Exception:
                    pass
        except Exception:
            for j, c in enumerate(batch):
                try:
                    emb = _embed([c])
                    if emb:
                        i = start + batch_start + j
                        ingest_document(content=c, title=title,
                                       source=f"materials/full/{title}",
                                       doc_id=f"materials:full:{title}:chunk{i}")
                        ok += 1
                except Exception:
                    pass

        if (batch_start + BATCH_SIZE) % (BATCH_SIZE * 4) == 0:
            elapsed = time.time() - t0
            current = start + batch_start + BATCH_SIZE
            eta = elapsed / max(current - start, 1) * (total - current) if current > start else 0
            print(f"    [{min(current, total)}/{total}] {elapsed:.0f}s, ETA:{eta/60:.0f}min, KB:{get_knowledge_count()}", flush=True)

        book_prog["ingested"] = start + batch_start + len(batch)
        progress[title] = book_prog
        if (batch_start // BATCH_SIZE) % 10 == 0:
            save_progress(progress)

    book_prog["ingested"] = total
    book_prog["status"] = "done"
    progress[title] = book_prog
    save_progress(progress)

    elapsed = time.time() - t0
    print(f"    DONE: {total} chunks, {elapsed:.0f}s ({elapsed/60:.1f}min)", flush=True)
    return True


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=int, default=BATCH_SIZE)
    parser.add_argument('--start-from', type=int, default=0)
    args = parser.parse_args()

    BATCH_SIZE = args.batch

    if not os.path.isdir(TEXT_DIR):
        print(f"文本目录不存在: {TEXT_DIR}")
        print("先运行: python -m app.scripts.ocr_phase")
        sys.exit(1)

    txt_files = sorted([f for f in os.listdir(TEXT_DIR) if f.endswith('.txt')])
    print(f"=== Phase 2: 嵌入入库 ===")
    print(f"  文本文件: {len(txt_files)} 个")
    print(f"  Batch size: {BATCH_SIZE}")
    print(f"  知识库: {get_knowledge_count()}")
    print()

    progress = load_progress()
    total_start = time.time()

    for idx, fname in enumerate(txt_files):
        if idx < args.start_from:
            continue
        title = fname.replace('.txt', '')
        txt_path = os.path.join(TEXT_DIR, fname)
        size_mb = os.path.getsize(txt_path) / 1024 / 1024

        print(f"[{idx+1}/{len(txt_files)}] {title} ({size_mb:.1f}MB)", flush=True)
        try:
            process_book(title, txt_path, progress)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)

    progress = load_progress()
    done = sum(1 for v in progress.values() if v.get("status") == "done")
    total_chunks = sum(v.get("ingested", 0) for v in progress.values())
    elapsed = time.time() - total_start

    print(f"\n{'='*50}")
    print(f"嵌入完成: {done}/{len(txt_files)}本")
    print(f"  总chunks: {total_chunks}")
    print(f"  总耗时: {elapsed:.0f}s ({elapsed/3600:.1f}h)")
    print(f"  知识库: {get_knowledge_count()}")
