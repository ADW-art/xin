"""
高速并行 OCR 入库 — 利用多核 CPU

策略:
  1. pdfplumber 提取文字层 (快, ~0.1s/页)
  2. 文字为空的页 → Tesseract OCR (慢, ~2-5s/页)
  3. 4+ 进程并行处理不同的书
  4. OCR 完成后直接入库

用法:
  python app/scripts/fast_ocr.py           # 全量, 每本100页, 4进程
  python app/scripts/fast_ocr.py -n 8 --pages 200  # 8进程, 每本200页
"""

import io, json, os, re, subprocess, sys, tempfile, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PDF_BASE = "E:/code/github_clone/pdf-计算机专业资源/Some-Many-Books/PDF-file"
MATERIALS_DIR = os.path.join(os.path.dirname(__file__), "knowledge_materials")
DONE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "ocr_all_done.txt")
TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS = 200

# All queued scanned PDFs
def get_all_pending():
    already = set()
    if os.path.exists(DONE_FILE):
        with open(DONE_FILE, "r", encoding="utf-8") as f:
            already = set(line.strip() for line in f)
    # Also check old done files
    for f in ["pdf_ingest_done.txt", "ocr_done.txt"]:
        path = os.path.join(os.path.dirname(__file__), "..", "..", f)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fp:
                already.update(line.strip() for line in fp)

    todo = []
    # Main dir
    for root, dirs, files in os.walk(PDF_BASE):
        subj = os.path.basename(root)
        for f in files:
            if not f.lower().endswith(".pdf"): continue
            key = f"{subj}/{f}"
            if key not in already:
                todo.append((subj, f, os.path.join(root, f), key))
    # Materials
    for f in os.listdir(MATERIALS_DIR):
        if not f.lower().endswith(".pdf"): continue
        key = f"materials/{f}"
        if key not in already:
            todo.append(("materials", f, os.path.join(MATERIALS_DIR, f), key))
    return todo


def ocr_page(page):
    """Try pdfplumber first, fallback to Tesseract"""
    # Fast path: pdfplumber text extraction
    try:
        text = page.extract_text()
        if text and len(text.strip()) > 20:
            return text.strip()
    except:
        pass
    # Slow path: Tesseract OCR
    try:
        import numpy as np
        from PIL import Image
        img = page.to_image(resolution=150)
        pil_img = Image.fromarray(np.array(img.original))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            pil_img.save(tmp.name)
        out_base = tmp.name.replace(".png", "")
        subprocess.run([TESSERACT, tmp.name, out_base, "-l", "chi_sim+eng", "--psm", "6"],
                       capture_output=True, text=True, timeout=30)
        os.unlink(tmp.name)
        txt_file = out_base + ".txt"
        if os.path.exists(txt_file):
            with open(txt_file, "r", encoding="utf-8") as f:
                text = f.read().strip()
            os.unlink(txt_file)
            return text
    except:
        pass
    return ""


def process_one_book(args):
    """OCR one book → return (key, text, stats)"""
    subj, fname, path, key, max_pages = args
    import pdfplumber
    t0 = time.time()
    title = fname.rsplit(".", 1)[0][:60]

    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
        to_ocr = min(max_pages, total)
        pages_text = []
        fast_pages = 0

        for i in range(to_ocr):
            text = ocr_page(pdf.pages[i])
            if text:
                pages_text.append(text)

        # Clean
        cleaned = []
        for t in pages_text:
            lines = [l.strip() for l in t.split("\n") if len(l.strip()) > 10]
            cleaned.append("\n".join(lines))
        full = "\n\n".join(cleaned)

        elapsed = time.time() - t0
        return {
            "key": key, "title": title, "text": full,
            "pages": len(pages_text), "total_pages": total,
            "chars": len(full), "elapsed": elapsed,
        }


def ingest_results(results):
    """Batch ingest OCR results into ChromaDB"""
    from app.core.chroma_client import get_collection
    col = get_collection("knowledge_base")
    total_chunks = 0
    for r in results:
        if not r or len(r["text"]) < 500:
            continue
        chunks = []
        start = 0
        while start < len(r["text"]) and len(chunks) < MAX_CHUNKS:
            end = start + CHUNK_SIZE
            c = r["text"][start:end].strip()
            if c: chunks.append(c)
            start += CHUNK_SIZE - CHUNK_OVERLAP

        if not chunks:
            continue

        ids = [f'ocr:{r["title"]}:chunk{i}' for i in range(len(chunks))]
        metas = [{"title": r["title"], "source": r["key"], "chunk": i, "ocr": True}
                 for i in range(len(chunks))]
        try:
            col.add(documents=chunks, embeddings=[[0.0] * 1024] * len(chunks),
                    metadatas=metas, ids=ids)
            total_chunks += len(chunks)
        except Exception as e:
            # Fallback: add one by one
            for i, c in enumerate(chunks):
                try:
                    col.add(documents=[c], embeddings=[[0.0] * 1024],
                            metadatas=[metas[i]], ids=[ids[i]])
                    total_chunks += 1
                except:
                    pass
    return total_chunks


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--workers", type=int, default=6)
    parser.add_argument("--pages", type=int, default=100)
    parser.add_argument("--books", type=int, default=0, help="0=all")
    args = parser.parse_args()

    if not os.path.exists(TESSERACT):
        print(f"Tesseract 未找到: {TESSERACT}")
        sys.exit(1)

    todo = get_all_pending()
    if args.books > 0:
        todo = todo[:args.books]

    print(f"待处理: {len(todo)} 本")
    print(f"并行进程: {args.workers}")
    print(f"每本页数: {args.pages}")
    print(f"策略: pdfplumber(快) → Tesseract(慢, 仅空页)")
    print()

    start_time = time.time()

    # Phase 1: Parallel OCR
    tasks = [(s, f, p, k, args.pages) for s, f, p, k in todo]
    results = []
    done_count = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_one_book, t): t for t in tasks}
        for future in as_completed(futures):
            r = future.result()
            if r and r["chars"] > 0:
                results.append(r)
                done_count += 1
                print(f"[{done_count}/{len(todo)}] {r['title'][:40]} "
                      f"{r['pages']}/{r['total_pages']}页 {r['chars']}字 {r['elapsed']:.0f}s")
                with open(DONE_FILE, "a", encoding="utf-8") as f:
                    f.write(r["key"] + "\n")
            else:
                t = futures[future]
                with open(DONE_FILE, "a", encoding="utf-8") as f:
                    f.write(t[3] + "\n")

    ocr_time = time.time() - start_time
    print(f"\nOCR 完成: {done_count}/{len(todo)} 本, {ocr_time:.0f}s ({ocr_time/done_count:.0f}s/本)" if done_count else "\n无结果")

    # Phase 2: Batch ingest
    if results:
        print("入库中...")
        chunks = ingest_results(results)
        from app.core.chroma_client import get_collection
        kb_count = get_collection("knowledge_base").count()
        print(f"入库: {chunks} chunks, KB: {kb_count}")
        print(f"总耗时: {time.time()-start_time:.0f}s")
