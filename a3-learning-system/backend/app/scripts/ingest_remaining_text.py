"""
入库剩余 7 本文字版 PDF
"""
import io, sys, os, time, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.document_parser import parse_pdf
from app.services.rag_service import _embed, ingest_document, get_knowledge_count

MATERIALS_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_materials')
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'remaining_text_done.json')

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS = 200

BOOKS = [
    ("C Primer Plus（第6版）中文版", "C Primer Plus（第6版）中文版 (（美）史蒂芬·普拉达（Stephen Prata）[著], 姜佑[译]) (Z-Library).pdf"),
    ("GitHub入门与实践", "GitHub入门与实践 (大塚弘记) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("Python编程 从入门到实践", "Python编程  从入门到实践 = Python Crash Course (Eric Matthes) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("人工智能之知识图谱", "人工智能之知识图谱【文字版】 (主编, 李涓子, 刘佳, 编辑, 陶硕, 时嘉琪, 何杨, 唐丽杭 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("算法图解", "算法图解.pdf"),
    ("计算机组成与设计", "计算机组成与设计硬件软件接口 硬件软件接口(原书第五版) ([美] David A.Patterson John L.Hennessy) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("计算机网络 自顶向下方法", "计算机网络（原书第7版） 自顶向下方法 (James F. Kurose Keith W. Ross) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
]


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
    progress = {}
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            progress = json.load(f)

    total_start = time.time()
    for idx, (title, filename) in enumerate(BOOKS):
        if progress.get(title) == 'done':
            print(f"[{idx+1}/{len(BOOKS)}] SKIP {title}")
            continue

        path = os.path.join(MATERIALS_DIR, filename)
        if not os.path.exists(path):
            print(f"[{idx+1}/{len(BOOKS)}] MISS {title}")
            continue

        size_mb = os.path.getsize(path) / 1024 / 1024
        print(f"\n[{idx+1}/{len(BOOKS)}] {title} ({size_mb:.1f}MB)", flush=True)
        t0 = time.time()

        try:
            paras = parse_pdf(path, use_ocr=False)
        except Exception as e:
            print(f"  PARSE ERROR: {e}")
            continue

        cleaned = [p['content'].strip() for p in paras if len(p['content'].strip()) > 20]
        if not cleaned:
            print(f"  EMPTY after clean")
            continue

        full = '\n\n'.join(cleaned)
        chunks = chunk_text(full)
        print(f"  {len(cleaned)} paragraphs, {len(full)} chars, {len(chunks)} chunks", flush=True)

        ok = 0
        for i, c in enumerate(chunks):
            try:
                emb = _embed([c])[0]
                ingest_document(content=c, title=title, source=f"materials/{filename}",
                               doc_id=f"materials:{title}:chunk{i}")
                ok += 1
                if (i + 1) % 40 == 0:
                    elapsed = time.time() - t0
                    print(f"    [{i+1}/{len(chunks)}] {elapsed:.0f}s, KB: {get_knowledge_count()}", flush=True)
            except Exception as e:
                print(f"    CHUNK[{i}] ERR: {e}")

        elapsed = time.time() - t0
        print(f"  DONE: {ok}/{len(chunks)} chunks, {elapsed:.0f}s ({elapsed/60:.1f}min), KB: {get_knowledge_count()}", flush=True)

        progress[title] = 'done'
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"总耗时: {(time.time()-total_start)/60:.1f}min, 知识库: {get_knowledge_count()}")
