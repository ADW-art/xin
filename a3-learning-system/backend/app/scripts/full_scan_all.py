"""
全量扫描所有 OCR 教材 — 逐页 Tesseract → 批量嵌入 → 入库
支持断点续传：进度存 full_scan_progress.json，每10页保存一次
用法:
  python -m app.scripts.full_scan_all          # 全部处理
  python -m app.scripts.full_scan_all --books 3  # 只处理前3本
  python -m app.scripts.full_scan_all --start-from 5  # 从第5本开始
"""
import io, sys, os, time, json, re, subprocess, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.rag_service import _embed, ingest_document, get_knowledge_count

MATERIALS_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_materials')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '_full_scan_texts')
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'full_scan_progress.json')
TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS = 300  # Increased for full books
PDF_DPI = 200
BATCH_SIZE = 8  # Batch embed size

# All 20 OCR books with exact filenames
BOOKS = [
    ("算法导论", "算法导论（原书第3版） (Thomas H.Cormen,Charles E.Leiserson etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("编译原理", "编译原理 第二版 (Alfred V. Aho,Monica S.Lam, Ravi Sethi etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("离散数学及其应用", "离散数学及其应用（原书第8版） (Kenneth H.Rosen) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("人工智能_现代方法", "人工智能：一种现代的方法（第3版） (罗素 诺维格) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据库系统概念", "数据库系统概念 原书第6版 本科教学版 (Silberschatz，Korth，Sudarshan著 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据结构与算法分析C++", "数据结构与算法分析 C++语言描述.4th2016 (Mark Allen Weiss) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("C++程序设计语言", "C++程序设计语言.第1～3部分.原书第4版 (Bjarne Stroustrup) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据结构与算法分析", "数据结构与算法分析 (Weiss, Mark Allen·韦斯,韦斯) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("计算机网络", "计算机网络 (谢希仁) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("C++第4部分标准库", "C++ 程序设计语言：第4部分 标准库（原书第4版 (Bjarne Stroustrup) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("具体数学", "具体数学 计算机科学基础（第2版）.pdf"),
    ("密码编码学与网络安全", "密码编码学与网络安全 原理与实践 第七版 ( etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("Java Web程序设计", "Java Web程序设计任务教程 (黑马程序员) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("Python语言程序设计基础", "Python语言程序设计基础（第2版） (嵩天，礼欣，黄天羽 著) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("C语言程序设计", "C语言程序设计（第五版） (谭浩强) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("软件测试", "软件测试（原书第2版）(Software Testing, 2nd Edition) ([美] Ron Patton) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据库系统概论", "数据库系统概论（第5版） (王珊 萨师煊) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("高等数学", "高等数学 同济第七版7版 上册 习题全解指南 课后习题答案解析.pdf"),
    ("人工智能导论", "人工智能导论 (李德毅, 于剑, 中国人工智能学会, 马少平, 王万良, 李绢子) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据库系统概论习题", "数据库系统概论 (第5版) 习题解析与实验指导 (王珊, 张俊) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    # 新增 7 本 (2024-06-18)
    ("Redis设计与实现", "Redis设计与实现 (黄健宏) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("深入理解Nginx", "深入理解Nginx：模块开发与架构解析（第2版） (LinuxUnix技术丛书) (陶辉 著 [著, 陶辉]) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("分布式系统概念与设计", "分布式系统：概念与设计（原书第五版） ( etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("动手学PyTorch建模与应用", "动手学PyTorch建模与应用：从深度学习到大模型 (王国平) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("计算机操作系统教程", "清华大学计算机系列教材 计算机操作系统教程 (张尧学 宋虹 张高) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("TAOCP卷1", "计算机程序设计艺术（第一卷）：基本算法 (计算机程序设计艺术（第一卷）：基本算法) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("计算机组成原理", "计算机组成原理 (艾伦·克莱门茨 (Alan Clements)) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
]


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_progress(prog):
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)


def ocr_page(page, page_num: int) -> str:
    """OCR single page with Tesseract"""
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


def clean_line(line: str) -> str:
    line = line.strip()
    if not line or len(line) < 10:
        return ""
    if re.match(r"^\s*\d{1,4}\s*$", line):
        return ""
    if re.match(r"^[\s\-_=#*~·.•|/\\]+$", line):
        return ""
    return line


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


def ingest_chunks(title, filename, chunks, start_idx, t0):
    """Batch embed and ingest"""
    ok = 0
    for batch_start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[batch_start:batch_start + BATCH_SIZE]
        try:
            embs = _embed(batch)
            for j, emb in enumerate(embs):
                i = batch_start + j
                doc_id = f"materials:full:{title}:chunk{start_idx + i}"
                try:
                    ingest_document(
                        content=batch[j],
                        title=title,
                        source=f"materials/{filename}",
                        doc_id=doc_id,
                    )
                    ok += 1
                except Exception as e:
                    pass  # skip failed chunks
        except Exception as e:
            print(f"    batch embed error at {batch_start}: {e}")
            # Fall back to single embedding
            for j, c in enumerate(batch):
                try:
                    emb = _embed([c])
                    if emb:
                        i = batch_start + j
                        doc_id = f"materials:full:{title}:chunk{start_idx + i}"
                        ingest_document(content=c, title=title, source=f"materials/{filename}", doc_id=doc_id)
                        ok += 1
                except Exception:
                    pass

        if (batch_start + BATCH_SIZE) % 40 == 0:
            elapsed = time.time() - t0
            print(f"    [{batch_start + BATCH_SIZE}/{len(chunks)}] {elapsed:.0f}s, KB:{get_knowledge_count()}", flush=True)
    return ok


def process_book(title, filename, progress):
    """Process one book: OCR all pages → chunk → ingest"""
    path = os.path.join(MATERIALS_DIR, filename)
    if not os.path.exists(path):
        print(f"  MISS: {filename[:60]}")
        return False

    book_prog = progress.get(title, {"ocr_pages": 0, "ingested_chunks": 0, "total_pages": 0})
    if book_prog.get("status") == "done":
        print(f"  SKIP (已完成): {title}")
        return True

    import pdfplumber

    t0 = time.time()
    size_mb = os.path.getsize(path) / 1024 / 1024

    with pdfplumber.open(path) as pdf:
        total_pages = len(pdf.pages)
        start_page = book_prog.get("ocr_pages", 0)

        if start_page == 0:
            print(f"\n  [{title}] {size_mb:.0f}MB, {total_pages}页 (全量扫描)", flush=True)

        # --- Phase 1: OCR remaining pages ---
        all_text = ""
        ocr_text_path = os.path.join(OUTPUT_DIR, f"{title}.txt")
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # Load existing OCR text
        if start_page > 0 and os.path.exists(ocr_text_path):
            with open(ocr_text_path, 'r', encoding='utf-8') as f:
                all_text = f.read()
            print(f"  续扫: 第{start_page+1}页起 (已有{start_page}页)", flush=True)

        for i in range(start_page, total_pages):
            page_text = ocr_page(pdf.pages[i], i + 1)
            if page_text:
                # Clean and append
                cleaned = "\n".join(clean_line(l) for l in page_text.split("\n") if clean_line(l))
                if cleaned:
                    all_text += cleaned + "\n\n"

            # Save progress every 10 pages
            if (i + 1) % 10 == 0 or i == total_pages - 1:
                with open(ocr_text_path, 'w', encoding='utf-8') as f:
                    f.write(all_text)
                book_prog["ocr_pages"] = i + 1
                book_prog["total_pages"] = total_pages
                progress[title] = book_prog
                save_progress(progress)
                elapsed = time.time() - t0
                pct = (i + 1) * 100 // total_pages
                print(f"    OCR {i+1}/{total_pages} ({pct}%) {elapsed:.0f}s", flush=True)

        ocr_time = time.time() - t0
        total_chars = len(all_text)
        print(f"    OCR完成: {total_chars} chars, {ocr_time:.0f}s ({ocr_time/60:.1f}min)", flush=True)

        # --- Phase 2: Chunk + Ingest ---
        chunks = chunk_text(all_text)
        existing_chunks = book_prog.get("ingested_chunks", 0)
        new_chunks = chunks[existing_chunks:]
        print(f"    {len(chunks)} chunks total, {len(new_chunks)} new to ingest", flush=True)

        if new_chunks:
            ok = ingest_chunks(title, filename, new_chunks, existing_chunks, t0)
            book_prog["ingested_chunks"] = existing_chunks + ok
            progress[title] = book_prog
            save_progress(progress)

        book_prog["status"] = "done"
        book_prog["total_chars"] = total_chars
        progress[title] = book_prog
        save_progress(progress)

        total_time = time.time() - t0
        print(f"    DONE: {book_prog['ingested_chunks']} chunks, {total_time:.0f}s ({total_time/60:.1f}min), KB:{get_knowledge_count()}", flush=True)
        return True


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--books', type=int, default=len(BOOKS), help='处理几本')
    parser.add_argument('--start-from', type=int, default=0, help='从第几本开始')
    args = parser.parse_args()

    if not os.path.exists(TESSERACT):
        print(f"Tesseract 未找到: {TESSERACT}")
        sys.exit(1)

    progress = load_progress()
    done_count = sum(1 for v in progress.values() if v.get("status") == "done")
    start_kb = get_knowledge_count()

    print(f"=== 全量扫描 {len(BOOKS)} 本教材 ===")
    print(f"已完成: {done_count} 本, 知识库: {start_kb}")
    print()

    total_start = time.time()
    todo = BOOKS[args.start_from:args.start_from + args.books]

    for idx, (title, filename) in enumerate(todo):
        book_num = args.start_from + idx + 1
        print(f"[{book_num}/{len(BOOKS)}]", end="", flush=True)

        try:
            process_book(title, filename, progress)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            continue

    # Summary
    progress = load_progress()
    done = sum(1 for v in progress.values() if v.get("status") == "done")
    total_chars = sum(v.get("total_chars", 0) for v in progress.values())
    total_chunks = sum(v.get("ingested_chunks", 0) for v in progress.values())
    elapsed = time.time() - total_start

    print(f"\n{'='*50}")
    print(f"全量扫描完成: {done}/{len(BOOKS)} 本")
    print(f"  总字符数: {total_chars:,}")
    print(f"  总chunks: {total_chunks}")
    print(f"  总耗时: {elapsed:.0f}s ({elapsed/3600:.1f}h)")
    print(f"  知识库: {get_knowledge_count()}")
