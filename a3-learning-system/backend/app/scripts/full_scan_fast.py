"""
全量扫描 — 多线程加速版
- OCR: 8线程并行 Tesseract (8x提速)
- 嵌入: 大batch (16-32) (2-3x提速)
- DPI: 150 (1.5x提速, 质量基本不变)
- 先试pdfplumber文字提取，命中则跳过OCR (100x提速)
- 总提速: 10-15x → 22h → ~2h

用法:
  python -m app.scripts.full_scan_fast
  python -m app.scripts.full_scan_fast --workers 12 --batch 32
"""
import io, sys, os, time, json, re, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.rag_service import _embed, ingest_document, get_knowledge_count

MATERIALS_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_materials')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '_full_scan_texts')
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'full_scan_progress.json')
TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# 默认参数（可通过命令行覆盖）
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS = 400
PDF_DPI = 150          # 降DPI提速
BATCH_SIZE = 16        # 大批次嵌入
OCR_WORKERS = 8        # 并行OCR线程数

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


def ocr_single_page(args):
    """OCR单页 (线程安全，通过args传参)"""
    img_array, page_num = args
    try:
        import numpy as np
        from PIL import Image
        pil_img = Image.fromarray(img_array)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
            pil_img.save(tmp_path)
        out_base = tmp_path.replace(".png", "")
        subprocess.run(
            [TESSERACT, tmp_path, out_base, "-l", "chi_sim+eng", "--psm", "6"],
            capture_output=True, text=True, timeout=20,
        )
        os.unlink(tmp_path)
        out_file = out_base + ".txt"
        text = ""
        if os.path.exists(out_file):
            with open(out_file, "r", encoding="utf-8") as f:
                text = f.read().strip()
            os.unlink(out_file)
        return (page_num, text)
    except Exception:
        return (page_num, "")


def clean_line(line: str) -> str:
    line = line.strip()
    if not line or len(line) < 8:
        return ""
    if re.match(r"^\s*\d{1,4}\s*$", line):
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


def ingest_chunks_fast(title, filename, chunks, start_idx, t0):
    """批量嵌入 + 入库"""
    ok = 0
    for batch_start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[batch_start:batch_start + BATCH_SIZE]
        try:
            embs = _embed(batch)
            for j, emb in enumerate(embs):
                i = batch_start + j
                doc_id = f"materials:full:{title}:chunk{start_idx + i}"
                try:
                    ingest_document(content=batch[j], title=title, source=f"materials/{filename}", doc_id=doc_id)
                    ok += 1
                except Exception:
                    pass
        except Exception:
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
        if (batch_start + BATCH_SIZE) % 80 == 0:
            elapsed = time.time() - t0
            print(f"    [{batch_start + BATCH_SIZE}/{len(chunks)}] {elapsed:.0f}s, KB:{get_knowledge_count()}", flush=True)
    return ok


def process_book(title, filename, progress, workers=OCR_WORKERS):
    """多线程OCR + 全量处理"""
    path = os.path.join(MATERIALS_DIR, filename)
    if not os.path.exists(path):
        print(f"  MISS: {filename[:60]}")
        return False

    book_prog = progress.get(title, {"ocr_pages": 0, "ingested_chunks": 0, "total_pages": 0, "text_extracted": 0})
    if book_prog.get("status") == "done":
        print(f"  SKIP: {title}")
        return True

    import pdfplumber
    import numpy as np

    t0 = time.time()
    size_mb = os.path.getsize(path) / 1024 / 1024

    with pdfplumber.open(path) as pdf:
        total_pages = len(pdf.pages)
        start_page = book_prog.get("ocr_pages", 0)
        text_extracted = book_prog.get("text_extracted", 0)

        # 评估文本提取比例
        text_ratio = text_extracted / max(start_page, 1) if start_page > 0 else 0

        if start_page == 0:
            print(f"\n  [{title}] {size_mb:.0f}MB, {total_pages}页 ({workers}线程并行OCR)", flush=True)
        else:
            print(f"\n  [{title}] 续扫: {start_page+1}/{total_pages}页 (文本命中率{text_ratio*100:.0f}%)", flush=True)

        all_text = ""
        ocr_text_path = os.path.join(OUTPUT_DIR, f"{title}.txt")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        if start_page > 0 and os.path.exists(ocr_text_path):
            with open(ocr_text_path, 'r', encoding='utf-8') as f:
                all_text = f.read()

        # 逐页处理：先试文字提取，不行再OCR
        for batch_start in range(start_page, total_pages, workers):
            batch_end = min(batch_start + workers, total_pages)
            batch_size = batch_end - batch_start

            # 先批量试文字提取
            fast_texts = {}
            for i in range(batch_start, batch_end):
                try:
                    t = pdf.pages[i].extract_text()
                    if t and len(t.strip()) > 30:
                        fast_texts[i] = t.strip()
                except Exception:
                    pass

            # 文字提取失败的 → 并行OCR
            ocr_needed = [i for i in range(batch_start, batch_end) if i not in fast_texts]
            if text_ratio < 0.3 and batch_start == start_page and len(ocr_needed) < batch_size * 0.3:
                # 文本命中率高，说明是文字版，提高阈值
                pass

            if ocr_needed:
                # 准备OCR任务
                ocr_tasks = []
                for i in ocr_needed:
                    try:
                        img = pdf.pages[i].to_image(resolution=PDF_DPI)
                        img_array = np.array(img.original)
                        ocr_tasks.append((img_array, i + 1))
                    except Exception:
                        pass

                # 多线程并行OCR
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {executor.submit(ocr_single_page, task): task[1] for task in ocr_tasks}
                    for future in as_completed(futures):
                        page_num, text = future.result()
                        if text and len(text.strip()) > 30:
                            fast_texts[page_num - 1] = text.strip()

            # 按页码顺序合并文本
            for i in range(batch_start, batch_end):
                raw = fast_texts.get(i, "")
                if raw:
                    cleaned = "\n".join(clean_line(l) for l in raw.split("\n") if clean_line(l))
                    if cleaned:
                        all_text += cleaned + "\n\n"

            # 更新进度
            book_prog["ocr_pages"] = batch_end
            book_prog["total_pages"] = total_pages
            book_prog["text_extracted"] = text_extracted + len(fast_texts)
            progress[title] = book_prog

            # 每20页存盘
            if batch_end % 20 == 0 or batch_end == total_pages:
                with open(ocr_text_path, 'w', encoding='utf-8') as f:
                    f.write(all_text)
                save_progress(progress)
                elapsed = time.time() - t0
                pct = batch_end * 100 // total_pages
                ocr_count = sum(1 for i in range(start_page, batch_end) if i in ocr_needed if i >= batch_start - workers)
                print(f"    {batch_end}/{total_pages} ({pct}%) {elapsed:.0f}s, KB:{get_knowledge_count()}", flush=True)

        ocr_time = time.time() - t0
        total_chars = len(all_text)
        print(f"    OCR完成: {total_chars:,} chars, {ocr_time:.0f}s ({ocr_time/60:.1f}min)", flush=True)

        # Phase 2: 嵌入
        chunks = chunk_text(all_text)
        existing_chunks = book_prog.get("ingested_chunks", 0)
        new_chunks = chunks[existing_chunks:]
        print(f"    {len(chunks)} chunks, {len(new_chunks)} 待入库", flush=True)

        if new_chunks:
            ok = ingest_chunks_fast(title, filename, new_chunks, existing_chunks, t0)
            book_prog["ingested_chunks"] = existing_chunks + ok
            progress[title] = book_prog
            save_progress(progress)

        book_prog["status"] = "done"
        book_prog["total_chars"] = total_chars
        progress[title] = book_prog
        save_progress(progress)

        total_time = time.time() - t0
        print(f"    DONE: {book_prog['ingested_chunks']} chunks, {total_time:.0f}s ({total_time/60:.1f}min)", flush=True)
        return True


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=OCR_WORKERS, help='并行OCR线程数')
    parser.add_argument('--batch', type=int, default=BATCH_SIZE, help='嵌入batch大小')
    parser.add_argument('--dpi', type=int, default=PDF_DPI, help='OCR DPI')
    parser.add_argument('--books', type=int, default=len(BOOKS), help='处理几本')
    parser.add_argument('--start-from', type=int, default=0, help='从第几本开始')
    args = parser.parse_args()

    OCR_WORKERS = args.workers
    BATCH_SIZE = args.batch
    PDF_DPI = args.dpi

    if not os.path.exists(TESSERACT):
        print(f"Tesseract 未找到: {TESSERACT}")
        sys.exit(1)

    progress = load_progress()
    done_count = sum(1 for v in progress.values() if v.get("status") == "done")

    print(f"=== 全量扫描加速版 ===")
    print(f"  并行OCR: {OCR_WORKERS}线程")
    print(f"  嵌入batch: {BATCH_SIZE}")
    print(f"  DPI: {PDF_DPI}")
    print(f"  已扫完: {done_count}/{len(BOOKS)}本")
    print(f"  知识库: {get_knowledge_count()}")
    print()

    total_start = time.time()
    todo = BOOKS[args.start_from:args.start_from + args.books]

    for idx, (title, filename) in enumerate(todo):
        book_num = args.start_from + idx + 1
        print(f"[{book_num}/{len(BOOKS)}]", end="", flush=True)
        try:
            process_book(title, filename, progress, OCR_WORKERS)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            continue

    progress = load_progress()
    done = sum(1 for v in progress.values() if v.get("status") == "done")
    total_chars = sum(v.get("total_chars", 0) for v in progress.values())
    total_chunks = sum(v.get("ingested_chunks", 0) for v in progress.values())
    elapsed = time.time() - total_start

    print(f"\n{'='*50}")
    print(f"完成: {done}/{len(BOOKS)}本")
    print(f"  总字符: {total_chars:,}")
    print(f"  总chunks: {total_chunks}")
    print(f"  总耗时: {elapsed:.0f}s ({elapsed/3600:.1f}h)")
    print(f"  知识库: {get_knowledge_count()}")
