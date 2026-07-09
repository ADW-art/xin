"""
Phase 1: OCR ONLY — 多线程扫描所有页面 → 存为 txt
不嵌入！先攒齐所有文本再统一嵌入（避免进度丢失）

用法:
  python -m app.scripts.ocr_phase              # 全部27本
  python -m app.scripts.ocr_phase --workers 12  # 12线程
  python -m app.scripts.ocr_phase --start-from 5  # 从第5本开始
"""
import io, sys, os, time, json, re, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

MATERIALS_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_materials')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '_full_scan_texts')
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'ocr_phase_progress.json')
TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

PDF_DPI = 150
OCR_WORKERS = 10

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
    """OCR单页"""
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


def clean_line(line):
    line = line.strip()
    if not line or len(line) < 8:
        return ""
    if re.match(r"^\s*\d{1,4}\s*$", line):
        return ""
    return line


def process_book(title, filename, progress, workers):
    path = os.path.join(MATERIALS_DIR, filename)
    if not os.path.exists(path):
        print(f"  MISS: {filename[:60]}")
        return False

    book_prog = progress.get(title, {"ocr_pages": 0, "total_pages": 0})
    if book_prog.get("status") == "done":
        print(f"  SKIP: {title}")
        return True

    import pdfplumber
    import numpy as np

    t0 = time.time()
    with pdfplumber.open(path) as pdf:
        total_pages = len(pdf.pages)
        start_page = book_prog.get("ocr_pages", 0)

        if start_page == 0:
            size_mb = os.path.getsize(path) / 1024 / 1024
            print(f"\n  [{title}] {size_mb:.0f}MB, {total_pages}页", flush=True)
        else:
            print(f"\n  [{title}] 续扫: {start_page+1}/{total_pages}", flush=True)

        # 加载已有文本
        ocr_text_path = os.path.join(OUTPUT_DIR, f"{title}.txt")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        all_text = ""
        if start_page > 0 and os.path.exists(ocr_text_path):
            with open(ocr_text_path, 'r', encoding='utf-8') as f:
                all_text = f.read()

        # 逐批处理 (workers页一批)
        for batch_start in range(start_page, total_pages, workers):
            batch_end = min(batch_start + workers, total_pages)

            # 1. 先试文字提取 (瞬间)
            fast_texts = {}
            for i in range(batch_start, batch_end):
                try:
                    t = pdf.pages[i].extract_text()
                    if t and len(t.strip()) > 30:
                        fast_texts[i] = t.strip()
                except Exception:
                    pass

            # 2. 文字提取失败的 → 并行OCR
            ocr_needed = [i for i in range(batch_start, batch_end) if i not in fast_texts]
            if ocr_needed:
                ocr_tasks = []
                for i in ocr_needed:
                    try:
                        img = pdf.pages[i].to_image(resolution=PDF_DPI)
                        ocr_tasks.append((np.array(img.original), i + 1))
                    except Exception:
                        pass

                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {executor.submit(ocr_single_page, t): t[1] for t in ocr_tasks}
                    for future in as_completed(futures):
                        page_num, text = future.result()
                        if text and len(text.strip()) > 30:
                            fast_texts[page_num - 1] = text.strip()

            # 3. 按页码顺序合并
            for i in range(batch_start, batch_end):
                raw = fast_texts.get(i, "")
                if raw:
                    cleaned = "\n".join(clean_line(l) for l in raw.split("\n") if clean_line(l))
                    if cleaned:
                        all_text += cleaned + "\n\n"

            # 4. 保存进度
            book_prog["ocr_pages"] = batch_end
            book_prog["total_pages"] = total_pages
            progress[title] = book_prog

            if batch_end % (workers * 2) == 0 or batch_end == total_pages:
                with open(ocr_text_path, 'w', encoding='utf-8') as f:
                    f.write(all_text)
                save_progress(progress)
                elapsed = time.time() - t0
                pct = batch_end * 100 // total_pages
                text_chars = len(all_text)
                print(f"    {batch_end}/{total_pages} ({pct}%) {elapsed:.0f}s, {text_chars:,}字", flush=True)

        # 完成
        with open(ocr_text_path, 'w', encoding='utf-8') as f:
            f.write(all_text)
        book_prog["status"] = "done"
        book_prog["total_chars"] = len(all_text)
        progress[title] = book_prog
        save_progress(progress)

        elapsed = time.time() - t0
        pages_done = total_pages - start_page
        rate = pages_done / elapsed if elapsed > 0 else 0
        print(f"    DONE: {len(all_text):,}字, {elapsed:.0f}s ({rate:.1f}页/秒)", flush=True)
        return True


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=OCR_WORKERS)
    parser.add_argument('--start-from', type=int, default=0)
    parser.add_argument('--books', type=int, default=len(BOOKS))
    args = parser.parse_args()

    if not os.path.exists(TESSERACT):
        print(f"Tesseract 未找到: {TESSERACT}")
        sys.exit(1)

    progress = load_progress()
    done = sum(1 for v in progress.values() if v.get("status") == "done")
    print(f"=== OCR Phase 1: 多线程扫描 ({args.workers}线程) ===")
    print(f"  已完成: {done}/{len(BOOKS)}本")
    print()

    total_start = time.time()
    todo = BOOKS[args.start_from:args.start_from + args.books]

    for idx, (title, filename) in enumerate(todo):
        num = args.start_from + idx + 1
        print(f"[{num}/{len(BOOKS)}]", end="", flush=True)
        try:
            process_book(title, filename, progress, args.workers)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)

    progress = load_progress()
    done = sum(1 for v in progress.values() if v.get("status") == "done")
    total_chars = sum(v.get("total_chars", 0) for v in progress.values())
    elapsed = time.time() - total_start

    print(f"\n{'='*50}")
    print(f"OCR完成: {done}/{len(BOOKS)}本")
    print(f"  总字符: {total_chars:,}")
    print(f"  总耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"  文本目录: {OUTPUT_DIR}")
    print(f"\n下一步: python -m app.scripts.ingest_phase  # 嵌入入库")
