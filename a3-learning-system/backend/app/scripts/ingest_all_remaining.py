"""
入库所有剩余 PDF — 自动区分文字版/扫描版，断点续传
"""
import io, sys, os, time, json, re, subprocess, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.document_parser import parse_pdf
from app.services.rag_service import _embed, ingest_document, get_knowledge_count

MATERIALS_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_materials')
OCR_OUTPUT = os.path.join(os.path.dirname(__file__), '..', '..', '_ocr_output2')
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', '_all_remaining_done.json')
TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS = 200
OCR_PAGES = 60

# All remaining PDFs
BOOKS = [
    # === 文字版 (pdfplumber) ===
    ("Rust程序设计语言", "Rust 程序设计语言 简体中文版 (Steve Klabnik，Carol Nichols，Rust 中文社区译) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "text"),
    ("Rust权威指南", "Rust权威指南（社区翻译版） (Steve Klabnik, Carol Nichols etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "text"),
    ("算法基础-打开算法之门", "算法基础.打开算法之门 (算法基础.打开算法之门) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "text"),
    # === 扫描版 (Tesseract OCR) ===
    ("TCPIP详解卷1", "TCPIP详解 卷1：协议（原书第2版） (凯文 R. 福尔 (Kevin R. Fall) etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("统计学习方法", "统计学习方法（第2版） (李航) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("高等数学下册", "高等数学·下册 第七版 (同济大学数学系) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("大话数据结构", "大话数据结构.pdf", "scan"),
    ("数据结构算法与应用C++", "数据结构、算法与应用（原书第2版） C++语言描述 (Sartaj Sahni) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("深入理解机器学习", "深入理解机器学习：从原理到算法 (Shai Shalev  Shwartz Shai Ben David) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("计算机程序设计艺术卷1", "计算机程序设计艺术（第一卷）：基本算法 (计算机程序设计艺术（第一卷）：基本算法) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
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


def clean_ocr_text(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) < 10:
            continue
        if re.match(r"^\s*\d{1,4}\s*$", line):
            continue
        if re.match(r"^[\s\-_=#*~·.•|/\\]+$", line):
            continue
        lines.append(line)
    return "\n\n".join(lines)


def ocr_page(page, page_num: int) -> str:
    try:
        import numpy as np
        from PIL import Image
        img = page.to_image(resolution=200)
        pil_img = Image.fromarray(np.array(img.original))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
            pil_img.save(tmp_path)
        out_base = tmp_path.replace(".png", "")
        subprocess.run(
            [TESSERACT, tmp_path, out_base, "-l", "chi_sim+eng", "--psm", "6"],
            capture_output=True, text=True, timeout=30,
        )
        os.unlink(tmp_path)
        out_file = out_base + ".txt"
        if os.path.exists(out_file):
            with open(out_file, "r", encoding="utf-8") as f:
                text = f.read().strip()
            os.unlink(out_file)
            return text
    except Exception:
        pass
    return ""


def process_text_book(title, filename):
    path = os.path.join(MATERIALS_DIR, filename)
    if not os.path.exists(path):
        print(f"  MISS: {path}")
        return False

    t0 = time.time()
    print(f"\n  [{title}] 文字版解析中...", flush=True)
    try:
        paras = parse_pdf(path, use_ocr=False)
    except Exception as e:
        print(f"  PARSE ERROR: {e}")
        return False

    cleaned = [p['content'].strip() for p in paras if len(p['content'].strip()) > 20]
    if not cleaned:
        print(f"  EMPTY, 降级为OCR模式")
        return process_scan_book(title, filename)

    full = '\n\n'.join(cleaned)
    return ingest_chunks(title, filename, full, t0)


def process_scan_book(title, filename):
    import pdfplumber
    import numpy as np

    path = os.path.join(MATERIALS_DIR, filename)
    if not os.path.exists(path):
        print(f"  MISS: {path}")
        return False

    t0 = time.time()
    print(f"\n  [{title}] Tesseract OCR 前{OCR_PAGES}页...", flush=True)

    pages_text = []
    try:
        with pdfplumber.open(path) as pdf:
            total_pages = len(pdf.pages)
            n = min(OCR_PAGES, total_pages)
            for i in range(n):
                pt = ocr_page(pdf.pages[i], i + 1)
                if pt:
                    pages_text.append(pt)
                if (i + 1) % 15 == 0:
                    elapsed = time.time() - t0
                    print(f"    page {i+1}/{n} ({len(pages_text)} ok, {elapsed:.0f}s)", flush=True)
    except Exception as e:
        print(f"  PDF OPEN ERROR: {e}")
        return False

    if not pages_text:
        print(f"  OCR 结果为空")
        return False

    full = clean_ocr_text("\n\n".join(pages_text))
    print(f"  {len(pages_text)} pages, {len(full)} chars", flush=True)
    return ingest_chunks(title, filename, full, t0)


def ingest_chunks(title, filename, full_text, t0):
    chunks = chunk_text(full_text)
    print(f"  {len(full_text)} chars → {len(chunks)} chunks", flush=True)

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
    return True


if __name__ == '__main__':
    progress = {}
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            progress = json.load(f)

    total_start = time.time()
    for idx, (title, filename, mode) in enumerate(BOOKS):
        if progress.get(title) == 'done':
            print(f"[{idx+1}/{len(BOOKS)}] SKIP {title}")
            continue

        size_mb = os.path.getsize(os.path.join(MATERIALS_DIR, filename)) / 1024 / 1024 if os.path.exists(os.path.join(MATERIALS_DIR, filename)) else 0
        print(f"\n[{idx+1}/{len(BOOKS)}] {title} ({mode}, {size_mb:.0f}MB)", flush=True)

        if mode == "text":
            success = process_text_book(title, filename)
        else:
            success = process_scan_book(title, filename)

        if success:
            progress[title] = 'done'
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"总耗时: {(time.time()-total_start)/60:.1f}min, 知识库: {get_knowledge_count()}")
