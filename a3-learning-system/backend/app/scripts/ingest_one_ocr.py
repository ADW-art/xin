"""
单本扫描版 PDF → Tesseract OCR → 向量化入库
用法: python -m app.scripts.ingest_one_ocr "<文件名>" <标题> [--max-pages N]
"""
import io, sys, os, time, json, re, subprocess, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.rag_service import _embed, ingest_document, get_knowledge_count

MATERIALS_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_materials')
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'materials_ocr_done.json')
TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS = 150
PDF_DPI = 200


def ocr_page(page, page_num: int) -> str:
    """OCR single page using Tesseract subprocess"""
    try:
        import numpy as np
        from PIL import Image

        img = page.to_image(resolution=PDF_DPI)
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
    except Exception as e:
        if page_num <= 3:
            print(f"    第{page_num}页OCR失败: {e}")
    return ""


def clean_ocr_text(text: str) -> str:
    """清洗 OCR 输出"""
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('filename', help='PDF 文件名')
    parser.add_argument('title', nargs='?', default=None, help='标题(可选)')
    parser.add_argument('--max-pages', type=int, default=50, help='最大 OCR 页数')
    parser.add_argument('--dpi', type=int, default=200, help='OCR DPI')
    args = parser.parse_args()

    filename = args.filename
    title = args.title or filename.rsplit('.', 1)[0]
    path = os.path.join(MATERIALS_DIR, filename)

    if not os.path.exists(TESSERACT):
        print(f"Tesseract 未找到: {TESSERACT}")
        sys.exit(1)
    if not os.path.exists(path):
        print(f"文件不存在: {path}")
        sys.exit(1)

    progress = {}
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            progress = json.load(f)

    if progress.get(title) == 'done':
        print(f"SKIP: {title}")
        sys.exit(0)

    size_mb = os.path.getsize(path) / 1024 / 1024
    print(f"[{title}] {size_mb:.1f}MB, Tesseract OCR {args.max_pages}页 @{args.dpi}DPI", flush=True)
    t0 = time.time()

    import pdfplumber

    pages_text = []
    try:
        with pdfplumber.open(path) as pdf:
            total = len(pdf.pages)
            n = min(args.max_pages, total)
            print(f"  PDF {total}页, OCR前{n}页...", flush=True)
            for i in range(n):
                page_text = ocr_page(pdf.pages[i], i + 1)
                if page_text:
                    pages_text.append(page_text)
                if (i + 1) % 10 == 0:
                    elapsed = time.time() - t0
                    print(f"  page {i+1}/{n} ({len(pages_text)} ok, {elapsed:.0f}s)", flush=True)
    except Exception as e:
        print(f"  PDF OPEN ERROR: {e}")
        sys.exit(1)

    if not pages_text:
        print(f"  EMPTY - 无OCR结果")
        progress[title] = 'empty'
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        sys.exit(0)

    full_text = clean_ocr_text("\n\n".join(pages_text))
    print(f"  OCR清洗后: {len(full_text)} chars", flush=True)

    chunks = chunk_text(full_text)
    ocr_time = time.time() - t0
    print(f"  {len(chunks)} chunks, OCR耗时={ocr_time:.0f}s", flush=True)

    # Embed + ingest
    ok = 0
    for i, c in enumerate(chunks):
        try:
            emb = _embed([c])[0]
            ingest_document(content=c, title=title, source=f"materials/{filename}",
                           doc_id=f"materials:ocr:{title}:chunk{i}")
            ok += 1
            if (i + 1) % 30 == 0:
                elapsed = time.time() - t0
                print(f"  [{i+1}/{len(chunks)}] {elapsed:.0f}s, KB:{get_knowledge_count()}", flush=True)
        except Exception as e:
            print(f"  CHUNK[{i}] ERR: {e}")

    elapsed = time.time() - t0
    print(f"  DONE: {ok}/{len(chunks)} chunks, {elapsed:.0f}s ({elapsed/60:.1f}min)", flush=True)

    progress[title] = 'done'
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

    print(f"  知识库总量: {get_knowledge_count()}")
