"""
第三批入库 — 新添加的 PDF
"""
import io, sys, os, time, json, re, subprocess, tempfile
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.document_parser import parse_pdf
from app.services.rag_service import _embed, ingest_document, get_knowledge_count

MATERIALS_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_materials')
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', '_batch3_done.json')
TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS = 200
OCR_PAGES = 60

BOOKS = [
    # === 文字版 ===
    ("深入理解计算机系统", "深入理解计算机系统 (Randal E. Bryant, David R. O’Hallaron) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "text"),
    ("线性代数", "线性代数 (同济大学数学系) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "text"),
    ("Python深度学习实战", "Python_深度学习实战：75个有关神经网络建模、强化学习与迁移 (Python_深度学习实战：75个有关神经网络建模、强化学习与迁移) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "text"),
    # === 扫描版 ===
    ("机器学习_西瓜书", "机器学习 (周志华) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("机器学习导论", "机器学习导论（原书第3版） ([土耳其] 埃塞姆·阿培丁（EthemAlpaydin）) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("Java核心技术卷I", "Java核心技术·卷 I（原书第11版） (凯·S.霍斯特曼 (Cay S. Horstmann)) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("Java核心技术卷II", "Java核心技术·卷 II（原书第11版）：高级特性 (凯 S.霍斯特曼 (Cay S.Horstmann)) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("操作系统概念", "操作系统概念（原书第9版） ( etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("计算机操作系统", "计算机操作系统（第四版） (汤小丹) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("软件工程导论", "软件工程导论 (张海藩 牟永敏) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("软件工程导论学习辅导", "软件工程导论 (第6版) 学习辅导 (张海藩) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
    ("计算机系统架构与操作系统", "计算机系统：系统架构与操作系统的高度集成 (A MAI KEN SHANG ER LA MU A TA DE...) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "scan"),
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


def clean_ocr_text(text):
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) < 10:
            continue
        if re.match(r"^\s*\d{1,4}\s*$", line):
            continue
        lines.append(line)
    return "\n\n".join(lines)


def ocr_page(page):
    try:
        img = page.to_image(resolution=200)
        pil_img = Image.fromarray(np.array(img.original))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
            pil_img.save(tmp_path)
        out_base = tmp_path.replace(".png", "")
        subprocess.run([TESSERACT, tmp_path, out_base, "-l", "chi_sim+eng", "--psm", "6"],
                       capture_output=True, text=True, timeout=30)
        os.unlink(tmp_path)
        out_file = out_base + ".txt"
        if os.path.exists(out_file):
            with open(out_file, "r", encoding="utf-8") as f:
                text = f.read().strip()
            os.unlink(out_file)
            return text
    except:
        pass
    return ""


def ingest(title, filename, full_text, t0):
    chunks = chunk_text(full_text)
    print(f"  {len(full_text)} chars -> {len(chunks)} chunks", flush=True)
    ok = 0
    for i, c in enumerate(chunks):
        try:
            emb = _embed([c])[0]
            ingest_document(content=c, title=title, source=f"materials/{filename}",
                           doc_id=f"materials:{title}:chunk{i}")
            ok += 1
            if (i + 1) % 40 == 0:
                print(f"    [{i+1}/{len(chunks)}] {time.time()-t0:.0f}s, KB:{get_knowledge_count()}", flush=True)
        except Exception as e:
            print(f"    CHUNK[{i}] ERR: {e}")
    elapsed = time.time() - t0
    print(f"  DONE: {ok}/{len(chunks)}, {elapsed:.0f}s, KB:{get_knowledge_count()}", flush=True)
    return True


def process_text(title, filename):
    path = os.path.join(MATERIALS_DIR, filename)
    t0 = time.time()
    print(f"\n  [{title}] 文字解析...", flush=True)
    try:
        paras = parse_pdf(path, use_ocr=False)
    except Exception as e:
        print(f"  PARSE ERROR: {e}")
        return False
    cleaned = [p['content'].strip() for p in paras if len(p['content'].strip()) > 20]
    if not cleaned:
        print(f"  EMPTY, fallback to OCR")
        return process_scan(title, filename)
    full = '\n\n'.join(cleaned)
    return ingest(title, filename, full, t0)


def process_scan(title, filename):
    import pdfplumber
    path = os.path.join(MATERIALS_DIR, filename)
    t0 = time.time()
    print(f"\n  [{title}] OCR {OCR_PAGES}页...", flush=True)
    pages_text = []
    try:
        with pdfplumber.open(path) as pdf:
            n = min(OCR_PAGES, len(pdf.pages))
            for i in range(n):
                pt = ocr_page(pdf.pages[i])
                if pt and len(pt) > 10:
                    pages_text.append(pt)
                if (i + 1) % 15 == 0:
                    print(f"    page {i+1}/{n} ({len(pages_text)} ok, {time.time()-t0:.0f}s)", flush=True)
    except Exception as e:
        print(f"  ERROR: {e}")
        return False
    if not pages_text:
        print(f"  EMPTY")
        return False
    full = clean_ocr_text("\n\n".join(pages_text))
    print(f"  {len(pages_text)} pages, {len(full)} chars", flush=True)
    return ingest(title, filename, full, t0)


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
        path = os.path.join(MATERIALS_DIR, filename)
        if not os.path.exists(path):
            print(f"[{idx+1}/{len(BOOKS)}] MISS {title}")
            continue
        size_mb = os.path.getsize(path) / 1024 / 1024
        print(f"\n[{idx+1}/{len(BOOKS)}] {title} ({mode}, {size_mb:.0f}MB)", flush=True)
        success = process_text(title, filename) if mode == "text" else process_scan(title, filename)
        if success:
            progress[title] = 'done'
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"Total: {(time.time()-total_start)/60:.1f}min, KB:{get_knowledge_count()}")
