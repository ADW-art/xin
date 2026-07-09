"""
批量入库 knowledge_materials 目录下的 PDF
- 文字版: pdfplumber 直接提取
- 扫描版: PaddleOCR
支持断点续传
"""
import io, sys, os, time, json, re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.document_parser import parse_pdf
from app.services.rag_service import _embed, ingest_document, get_knowledge_count

MATERIALS_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_materials')
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'materials_ingest_done.json')

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS = 200

# 需要处理的 PDF 列表 (扫描结果)
TEXT_PDFS = [
    ("C程序设计（第五版）学习辅导", "C程序设计（第五版）学习辅导 (谭浩强)（OCR） (谭浩强) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("内网渗透技术", "内网渗透技术 (吴丽进 主编；苗春雨 主编；郑州 副主编；雷珊珊 副主编；王伦 副主编) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("大数据技术原理与应用", "大数据技术原理与应用(第三版) (林子雨) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("啊哈!算法", "啊哈!算法_.pdf"),
]

SCAN_PDFS = [
    ("C++程序设计语言", "C++程序设计语言.第1～3部分.原书第4版 (Bjarne Stroustrup) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("Python语言程序设计基础", "Python语言程序设计基础（第2版） (嵩天，礼欣，黄天羽 著) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("人工智能导论", "人工智能导论 (李德毅, 于剑, 中国人工智能学会, 马少平, 王万良, 李绢子) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("人工智能：一种现代的方法", "人工智能：一种现代的方法（第3版） (罗素 诺维格) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("具体数学", "具体数学 计算机科学基础（第2版）.pdf"),
    ("密码编码学与网络安全", "密码编码学与网络安全 原理与实践 第七版 ( etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据库系统概念", "数据库系统概念 原书第6版 本科教学版 (Silberschatz，Korth，Sudarshan著 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据库系统概论习题解析", "数据库系统概论 (第5版) 习题解析与实验指导 (王珊, 张俊) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据库系统概论", "数据库系统概论（第5版） (王珊 萨师煊) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据结构与算法分析", "数据结构与算法分析 (Weiss, Mark Allen·韦斯,韦斯) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("数据结构与算法分析C++", "数据结构与算法分析 C++语言描述.4th2016 (Mark Allen Weiss) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("离散数学及其应用", "离散数学及其应用（原书第8版） (Kenneth H.Rosen) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("算法导论", "算法导论（原书第3版） (Thomas H.Cormen,Charles E.Leiserson etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("编译原理", "编译原理 第二版 (Alfred V. Aho,Monica S.Lam, Ravi Sethi etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("编译原理(大)", "计算机科学丛书：编译原理（第2版） ([美]Alfred V.Aho, [美]Monica S.Lam etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("计算机网络(谢希仁)", "计算机网络 (谢希仁) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("软件测试", "软件测试（原书第2版）(Software Testing, 2nd Edition) ([美] Ron Patton) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
    ("高等数学", "高等数学 同济第七版7版 上册 习题全解指南 课后习题答案解析.pdf"),
]


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_progress(progress):
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


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


def process_text_pdf(title, filename):
    """处理文字版 PDF"""
    path = os.path.join(MATERIALS_DIR, filename)
    if not os.path.exists(path):
        print(f"  MISS: {path}")
        return False

    t0 = time.time()
    print(f"\n  [{title}] 解析中...", flush=True)

    try:
        paras = parse_pdf(path, use_ocr=False)
    except Exception as e:
        print(f"  PARSE ERROR: {e}")
        return False

    cleaned = [p['content'].strip() for p in paras if len(p['content'].strip()) > 20]
    if not cleaned:
        print(f"  EMPTY after clean, trying with OCR fallback...")
        try:
            paras = parse_pdf(path, use_ocr=True)
            cleaned = [p['content'].strip() for p in paras if len(p['content'].strip()) > 20]
        except Exception as e:
            print(f"  OCR fallback also failed: {e}")
            return False

    if not cleaned:
        print(f"  STILL EMPTY")
        return False

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
            if (i + 1) % 30 == 0:
                print(f"    chunk {i+1}/{len(chunks)}", flush=True)
        except Exception as e:
            print(f"    chunk[{i}] ERR: {e}")

    elapsed = time.time() - t0
    print(f"  DONE: {ok}/{len(chunks)} chunks, {elapsed:.0f}s", flush=True)
    return True


def process_scan_pdf(title, filename, max_pages=60):
    """处理扫描版 PDF (OCR)"""
    import pdfplumber
    import numpy as np

    path = os.path.join(MATERIALS_DIR, filename)
    if not os.path.exists(path):
        print(f"  MISS: {path}")
        return False

    t0 = time.time()
    print(f"\n  [{title}] OCR 前{max_pages}页...", flush=True)

    # 懒加载 PaddleOCR
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(lang='ch')

    pages_text = []
    try:
        with pdfplumber.open(path) as pdf:
            total_pages = len(pdf.pages)
            n = min(max_pages, total_pages)
            for i in range(n):
                try:
                    page = pdf.pages[i]
                    img = page.to_image(resolution=200)
                    img_array = np.array(img.original)
                    result = ocr.ocr(img_array)
                    if result and result[0]:
                        lines = []
                        for line_info in result[0]:
                            if len(line_info) > 1 and len(line_info[1]) > 0:
                                text = line_info[1][0]
                                if text:
                                    lines.append(text)
                        if lines:
                            pages_text.append('\n'.join(lines))
                except Exception as e:
                    pass  # skip failed pages

                if (i + 1) % 15 == 0:
                    elapsed = time.time() - t0
                    print(f"    page {i+1}/{n}, {elapsed:.0f}s", flush=True)
    except Exception as e:
        print(f"  PDF OPEN ERROR: {e}")
        return False

    if not pages_text:
        print(f"  OCR 结果为空")
        return False

    full_text = '\n\n'.join(pages_text)
    # 简单清洗
    full_text = re.sub(r'\n{3,}', '\n\n', full_text)
    full_text = re.sub(r'\s{2,}', ' ', full_text)

    chunks = chunk_text(full_text)
    print(f"  {len(pages_text)} pages, {len(full_text)} chars, {len(chunks)} chunks", flush=True)

    ok = 0
    for i, c in enumerate(chunks):
        try:
            emb = _embed([c])[0]
            ingest_document(content=c, title=title, source=f"materials/{filename}",
                           doc_id=f"materials:{title}:chunk{i}")
            ok += 1
            if (i + 1) % 20 == 0:
                print(f"    chunk {i+1}/{len(chunks)}", flush=True)
        except Exception as e:
            print(f"    chunk[{i}] ERR: {e}")

    elapsed = time.time() - t0
    print(f"  DONE: {ok}/{len(chunks)} chunks, {elapsed:.0f}s", flush=True)
    return True


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', action='store_true', help='处理文字版 PDF')
    parser.add_argument('--scan', action='store_true', help='处理扫描版 PDF')
    parser.add_argument('--all', action='store_true', help='处理所有')
    parser.add_argument('--max-pages', type=int, default=60, help='扫描版每本最多 OCR 页数')
    parser.add_argument('--start-from', type=int, default=0, help='扫描版从第几本开始')
    args = parser.parse_args()

    progress = load_progress()

    if args.text or args.all:
        print("=" * 50)
        print(f"文字版 PDF: {len(TEXT_PDFS)} 本")
        print("=" * 50)
        for title, filename in TEXT_PDFS:
            key = f"text:{title}"
            if progress.get(key) == "done":
                print(f"  SKIP {title}")
                continue
            if process_text_pdf(title, filename):
                progress[key] = "done"
                save_progress(progress)
            print(f"  知识库: {get_knowledge_count()} 条", flush=True)

    if args.scan or args.all:
        print("=" * 50)
        print(f"扫描版 PDF: {len(SCAN_PDFS)} 本 (每本{args.max_pages}页)")
        print("=" * 50)
        for i, (title, filename) in enumerate(SCAN_PDFS):
            if i < args.start_from:
                continue
            key = f"scan:{title}"
            if progress.get(key) == "done":
                print(f"  SKIP {title}")
                continue
            if process_scan_pdf(title, filename, max_pages=args.max_pages):
                progress[key] = "done"
                save_progress(progress)
            print(f"  知识库: {get_knowledge_count()} 条", flush=True)

    print(f"\n最终知识库: {get_knowledge_count()} 条")
