"""
分步式扫描版 PDF 入库流水线
步骤1: OCR 所有书 → 存为 _ocr_output/*.txt (只跑 OCR)
步骤2: 批量入库 _ocr_output/*.txt (只做向量化+入库)
支持断点续传
"""
import io, sys, os, time, json, re, subprocess, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.rag_service import _embed, ingest_document, get_knowledge_count

MATERIALS_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_materials')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '_ocr_output')
OCR_DONE_FILE = os.path.join(os.path.dirname(__file__), '..', '..', '_ocr_step1_done.json')
INGEST_DONE_FILE = os.path.join(os.path.dirname(__file__), '..', '..', '_ocr_step2_done.json')
TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS = 120
PDF_DPI = 200

# 待处理扫描版书单
SCAN_BOOKS = [
    ("算法导论", "算法导论（原书第3版） (Thomas H.Cormen,Charles E.Leiserson etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据结构与算法分析", "数据结构与算法分析 (Weiss, Mark Allen·韦斯,韦斯) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据库系统概论", "数据库系统概论（第5版） (王珊 萨师煊) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("计算机网络", "计算机网络 (谢希仁) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("离散数学及其应用", "离散数学及其应用（原书第8版） (Kenneth H.Rosen) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("编译原理", "编译原理 第二版 (Alfred V. Aho,Monica S.Lam, Ravi Sethi etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("C++程序设计语言", "C++程序设计语言.第1～3部分.原书第4版 (Bjarne Stroustrup) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("人工智能:现代方法", "人工智能：一种现代的方法（第3版） (罗素 诺维格) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("Python语言程序设计基础", "Python语言程序设计基础（第2版） (嵩天，礼欣，黄天羽 著) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("密码编码学与网络安全", "密码编码学与网络安全 原理与实践 第七版 ( etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据库系统概念", "数据库系统概念 原书第6版 本科教学版 (Silberschatz，Korth，Sudarshan著 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据结构与算法分析C++", "数据结构与算法分析 C++语言描述.4th2016 (Mark Allen Weiss) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("高等数学", "高等数学 同济第七版7版 上册 习题全解指南 课后习题答案解析.pdf"),
    ("人工智能导论", "人工智能导论 (李德毅, 于剑, 中国人工智能学会, 马少平, 王万良, 李绢子) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("具体数学", "具体数学 计算机科学基础（第2版）.pdf"),
    ("软件测试", "软件测试（原书第2版）(Software Testing, 2nd Edition) ([美] Ron Patton) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据库系统概论习题", "数据库系统概论 (第5版) 习题解析与实验指导 (王珊, 张俊) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
]


def ocr_page(page, page_num: int) -> str:
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
    except Exception:
        pass
    return ""


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


def step1_ocr(max_pages: int = 50, start_from: int = 0, count: int = None):
    """仅执行 Tesseract OCR，结果存为 txt"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    done = {}
    if os.path.exists(OCR_DONE_FILE):
        with open(OCR_DONE_FILE, 'r', encoding='utf-8') as f:
            done = json.load(f)

    todo = SCAN_BOOKS[start_from:]
    if count:
        todo = todo[:count]

    print(f"=== STEP 1: OCR ({len(todo)} 本, 每本{max_pages}页) ===")
    for idx, (title, filename) in enumerate(todo):
        if done.get(title) == 'done':
            print(f"[{start_from+idx+1}/{len(SCAN_BOOKS)}] SKIP {title}")
            continue

        path = os.path.join(MATERIALS_DIR, filename)
        if not os.path.exists(path):
            print(f"[{start_from+idx+1}/{len(SCAN_BOOKS)}] MISS {title}")
            continue

        print(f"\n[{start_from+idx+1}/{len(SCAN_BOOKS)}] {title}", flush=True)
        t0 = time.time()

        import pdfplumber
        pages_text = []
        with pdfplumber.open(path) as pdf:
            total = len(pdf.pages)
            n = min(max_pages, total)
            for i in range(n):
                pt = ocr_page(pdf.pages[i], i + 1)
                if pt:
                    pages_text.append(pt)
                if (i + 1) % 15 == 0:
                    print(f"  page {i+1}/{n} ({len(pages_text)} ok, {time.time()-t0:.0f}s)", flush=True)

        if not pages_text:
            print(f"  EMPTY")
            done[title] = 'empty'
            with open(OCR_DONE_FILE, 'w', encoding='utf-8') as f:
                json.dump(done, f, ensure_ascii=False, indent=2)
            continue

        full = clean_ocr_text("\n\n".join(pages_text))
        out_path = os.path.join(OUTPUT_DIR, f"{title}.txt")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(full)

        elapsed = time.time() - t0
        print(f"  OCR完成: {len(full)} chars → {out_path} ({elapsed:.0f}s)", flush=True)

        done[title] = 'done'
        with open(OCR_DONE_FILE, 'w', encoding='utf-8') as f:
            json.dump(done, f, ensure_ascii=False, indent=2)

    print(f"\nSTEP1 完成: {sum(1 for v in done.values() if v == 'done')} 本已OCR")


def step2_ingest():
    """将 _ocr_output/*.txt 向量化入库"""
    if not os.path.isdir(OUTPUT_DIR):
        print("OCR 输出目录不存在，先运行 step1")
        return

    done = {}
    if os.path.exists(INGEST_DONE_FILE):
        with open(INGEST_DONE_FILE, 'r', encoding='utf-8') as f:
            done = json.load(f)

    txt_files = sorted([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.txt')])
    print(f"=== STEP 2: 入库 ({len(txt_files)} 个txt文件) ===")

    for fname in txt_files:
        title = fname.replace('.txt', '')
        if done.get(title) == 'done':
            print(f"  SKIP {title}")
            continue

        fpath = os.path.join(OUTPUT_DIR, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            text = f.read()

        chunks = chunk_text(text)
        print(f"\n  [{title}] {len(text)} chars → {len(chunks)} chunks", flush=True)
        t0 = time.time()

        ok = 0
        for i, c in enumerate(chunks):
            try:
                emb = _embed([c])[0]
                ingest_document(content=c, title=title, source=f"materials/ocr/{fname}",
                               doc_id=f"materials:ocr:{title}:chunk{i}")
                ok += 1
                if (i + 1) % 40 == 0:
                    print(f"    [{i+1}/{len(chunks)}] {time.time()-t0:.0f}s", flush=True)
            except Exception as e:
                print(f"    CHUNK[{i}] ERR: {e}")

        elapsed = time.time() - t0
        print(f"  DONE: {ok}/{len(chunks)}, {elapsed:.0f}s, KB:{get_knowledge_count()}", flush=True)

        done[title] = 'done'
        with open(INGEST_DONE_FILE, 'w', encoding='utf-8') as f:
            json.dump(done, f, ensure_ascii=False, indent=2)

    print(f"\nSTEP2 完成: {sum(1 for v in done.values() if v == 'done')} 本书已入库")
    print(f"知识库总量: {get_knowledge_count()}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='分步式 OCR 入库流水线')
    parser.add_argument('--step1', action='store_true', help='仅 OCR，结果存 txt')
    parser.add_argument('--step2', action='store_true', help='仅向量化入库 txt')
    parser.add_argument('--all', action='store_true', help='先OCR再入库')
    parser.add_argument('--max-pages', type=int, default=50, help='每本 OCR 页数')
    parser.add_argument('--start-from', type=int, default=0, help='从第几本开始')
    parser.add_argument('--count', type=int, default=None, help='处理几本')
    args = parser.parse_args()

    if not os.path.exists(TESSERACT):
        print(f"Tesseract 未找到: {TESSERACT}")
        sys.exit(1)

    if args.step1 or args.all:
        step1_ocr(max_pages=args.max_pages, start_from=args.start_from, count=args.count)
    if args.step2:
        step2_ingest()
    if not args.step1 and not args.step2 and not args.all:
        step1_ocr(max_pages=args.max_pages, start_from=args.start_from, count=args.count)
        step2_ingest()
