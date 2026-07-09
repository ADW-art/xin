"""
单本 PDF 快速入库 (从 knowledge_materials 目录)
用法: python -m app.scripts.ingest_one_book "<文件名>"
"""
import io, sys, os, time, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.document_parser import parse_pdf
from app.services.rag_service import _embed, ingest_document, get_knowledge_count

MATERIALS_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_materials')
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'materials_ingest_done.json')

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS = 200


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


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python -m app.scripts.ingest_one_book '<文件名>' [标题]")
        sys.exit(1)

    filename = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else filename.rsplit('.', 1)[0]
    path = os.path.join(MATERIALS_DIR, filename)

    if not os.path.exists(path):
        print(f"文件不存在: {path}")
        sys.exit(1)

    progress = {}
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            progress = json.load(f)

    key = title
    if progress.get(key) == 'done':
        print(f"SKIP: {title} (已完成)")
        sys.exit(0)

    size_mb = os.path.getsize(path) / 1024 / 1024
    print(f"[{title}] {size_mb:.1f}MB", flush=True)
    t0 = time.time()

    # 1. 解析
    try:
        paras = parse_pdf(path, use_ocr=False)
    except Exception as e:
        print(f"  PARSE ERROR: {e}")
        sys.exit(1)

    cleaned = [p['content'].strip() for p in paras if len(p['content'].strip()) > 20]
    print(f"  {len(cleaned)} paragraphs", flush=True)

    if not cleaned:
        print(f"  EMPTY, trying OCR fallback...")
        try:
            paras = parse_pdf(path, use_ocr=True)
            cleaned = [p['content'].strip() for p in paras if len(p['content'].strip()) > 20]
        except Exception as e:
            print(f"  OCR fallback failed: {e}")
            sys.exit(1)

    if not cleaned:
        print(f"  STILL EMPTY")
        progress[key] = 'empty'
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        sys.exit(0)

    full = '\n\n'.join(cleaned)
    chunks = chunk_text(full)
    print(f"  {len(full)} chars → {len(chunks)} chunks", flush=True)

    # 2. 逐块向量化入库
    ok = 0
    for i, c in enumerate(chunks):
        try:
            emb = _embed([c])[0]
            ingest_document(content=c, title=title, source=f"materials/{filename}",
                           doc_id=f"materials:{title}:chunk{i}")
            ok += 1
            if (i + 1) % 50 == 0:
                elapsed = time.time() - t0
                print(f"  [{i+1}/{len(chunks)}] {elapsed:.0f}s, KB: {get_knowledge_count()}", flush=True)
        except Exception as e:
            print(f"  CHUNK[{i}] ERR: {e}")

    elapsed = time.time() - t0
    print(f"  DONE: {ok}/{len(chunks)} chunks, {elapsed:.0f}s ({elapsed/60:.1f}min)", flush=True)

    progress[key] = 'done'
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

    print(f"  知识库总量: {get_knowledge_count()}")
