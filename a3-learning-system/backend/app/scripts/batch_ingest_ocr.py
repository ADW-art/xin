"""
批量 OCR 扫描版 PDF → 向量化入库
=================================
策略：
  1. 单例 PaddleOCR 实例（避免每页重复加载模型）
  2. 只处理前 --max-pages 页（默认100，因 OCR 2-5秒/页）
  3. --books N 控制本批处理几本书
  4. 进度持久化到 ocr_ingest_done.json，支持断点续跑
  5. 鲁棒的错误处理：单页失败 → 跳过继续
  6. OCR 输出清洗：去噪、合并断行、修正常见错误

用法：
  python app/scripts/batch_ingest_ocr.py --max-pages 100 --books 5
  python app/scripts/batch_ingest_ocr.py --max-pages 50 --books 2 --start-from 3
"""

import argparse
import io
import json
import os
import re
import sys
import time
from pathlib import Path

# 项目根路径注入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ============================================================
# 配置常量
# ============================================================

PDF_BASE = "E:/code/github_clone/pdf-计算机专业资源/Some-Many-Books/PDF-file"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS_PER_BOOK = 150
PDF_RESOLUTION = 200  # DPI，越高OCR越准但越慢

# ============================================================
# 优先级扫描书单（15本 CS 核心圣经）
# ============================================================

PRIORITY_OCR = [
    ("algorithms", "算法导论（第2版）.pdf"),
    ("algorithms", "算法（第4版）.pdf"),
    ("algorithms", "数据结构与算法分析：C语言描述（第2版）.pdf"),
    ("computer-system", "深入理解计算机系统.pdf"),
    ("computer-system", "编译原理（第2版）.pdf"),
    ("computer-system", "计算机程序的构造和解释（第2版）.pdf"),
    ("computer-system", "现代操作系统（第3版）.pdf"),
    ("linux", "UNIX环境高级编程(第三版).pdf"),
    ("linux", "UNIX网络编程卷1：套接字API.pdf"),
    ("mysql", "高性能MySQL（第3版）中文版.pdf"),
    ("redis", "Redis设计与实现.pdf"),
    ("design-pattern", "HeadFirst设计模式.pdf"),
    ("design-pattern", "设计模式：可复用面向对象软件的基础.pdf"),
    ("java", "Java编程思想（第4版）.pdf"),
    ("system", "企业应用架构模式.pdf"),
]


# ============================================================
# OCR 输出清洗
# ============================================================

# 常见 OCR 错误纠正词典
OCR_CORRECTIONS = {
    "算汔": "算法",
    "数捃": "数据",
    "结枃": "结构",
    "计笪机": "计算机",
    "操亻": "操作",
    "系纺": "系统",
    "编泽": "编译",
    "网绍": "网络",
    "协义": "协议",
    "存偖": "存储",
    "进稆": "进程",
    "线稆": "线程",
    "内f": "内存",
    "设i": "设计",
    "模工": "模式",
    "枟架": "框架",
    "函數": "函数",
    "变糧": "变量",
    "指钅": "指针",
    "对豢": "对象",
    "类刖": "类型",
    "递丬": "递归",
    "排孖": "排序",
    "搜绱": "搜索",
    "哈帀": "哈希",
    "二义树": "二叉树",
    "图汊": "图论",
    "优卮": "优化",
    "缓f": "缓存",
    "索弓": "索引",
    "事勹": "事务",
    "并叐": "并发",
    "中闿件": "中间件",
    "微服勹": "微服务",
    "容噐": "容器",
    "虚似": "虚拟",
    "分巿式": "分布式",
    "机噐": "机器",
    "人巟": "人工",
    "智胿": "智能",
    "神缐": "神经",
    "网绚": "网络",
    "嵌亼": "嵌入",
    "编稆": "编程",
    "软仵": "软件",
    "硬仵": "硬件",
    "数捃库": "数据库",
    "文仵": "文件",
    "目彔": "目录",
    "路徂": "路径",
    "进稆间": "进程间",
    "套掱字": "套接字",
    "负軝": "负载",
    "性胿": "性能",
    "高并叐": "高并发",
    "流式": "流式",
    "管迌": "管道",
    "信叻": "信号",
    "共亪": "共享",
    "互斥": "互斥",
    "同歨": "同步",
    "异歨": "异步",
    "阻壱": "阻塞",
    "非阻壱": "非阻塞",
    "多稆": "多路",
    "复甬": "复用",
}


def clean_ocr_line(line: str) -> str:
    """清洗单行 OCR 输出"""
    line = line.strip()
    if not line:
        return ""

    # 去除纯数字页码残留
    if re.match(r"^\s*\d{1,4}\s*$", line):
        return ""

    # 去除仅含特殊字符的行（水印/噪点）
    if re.match(r"^[\s\-_=#*~·.•|/\\]+$", line):
        return ""

    # 去除过短噪声行（< 2 个有效中英文字符）
    chinese_chars = len(re.findall(r"[一-鿿]", line))
    english_words = len(re.findall(r"[a-zA-Z]+", line))
    if chinese_chars + english_words < 2:
        return ""

    # 修正常见 OCR 错误
    for wrong, correct in OCR_CORRECTIONS.items():
        line = line.replace(wrong, correct)

    # 合并被 OCR 拆分的英文单词（如 "algo rithm" → "algorithm"）
    line = re.sub(r"([a-z]) ([a-z])", lambda m: f"{m.group(1)}{m.group(2)}", line)

    # 恢复常见标点（OCR 可能丢失中文标点）
    line = line.replace("  ", " ")
    line = re.sub(r"([一-鿿])([A-Za-z0-9])", r"\1 \2", line)
    line = re.sub(r"([A-Za-z0-9])([一-鿿])", r"\1 \2", line)

    return line


def clean_ocr_text(pages_text: list[str]) -> str:
    """清洗整本书的 OCR 输出，返回纯文本"""
    cleaned_lines = []
    for page_text in pages_text:
        if not page_text:
            continue
        for line in page_text.split("\n"):
            cleaned = clean_ocr_line(line)
            if cleaned:
                cleaned_lines.append(cleaned)

    if not cleaned_lines:
        return ""

    # 合并连续的短行（OCR 常将一句话拆成多行）
    merged = []
    buffer = ""
    for line in cleaned_lines:
        # 如果当前行以标点结尾，视为完整句；否则可能被截断，追加到buffer
        ends_with_punct = bool(re.search(r"[。！？.!?）\)」』]$", line))
        if not buffer:
            buffer = line
        elif len(re.findall(r"[一-鿿]", buffer)) < 20 and not ends_with_punct:
            buffer += line  # 短行且不以标点结尾→合并
        else:
            merged.append(buffer)
            buffer = line
        if ends_with_punct:
            merged.append(buffer)
            buffer = ""
    if buffer:
        merged.append(buffer)

    return "\n\n".join(merged)


# ============================================================
# 文本分块
# ============================================================

def chunk_text(text: str, max_chunks: int = MAX_CHUNKS_PER_BOOK) -> list[str]:
    """滑动窗口分块（与 batch_ingest_text.py 一致）"""
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len and len(chunks) < max_chunks:
        end = start + CHUNK_SIZE
        chunk = text[start:end].strip()
        if chunk and len(chunk) > 30:  # 过滤过短块
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ============================================================
# 单例 PaddleOCR
# ============================================================

_ocr_instance = None


def get_ocr():
    """获取全局单例 PaddleOCR 实例"""
    global _ocr_instance
    if _ocr_instance is None:
        from paddleocr import PaddleOCR
        print("初始化 PaddleOCR（单例，仅加载一次）...")
        t = time.time()
        _ocr_instance = PaddleOCR(lang="ch")
        print(f"PaddleOCR 初始化完成，耗时 {time.time() - t:.0f}s")
    return _ocr_instance


# ============================================================
# 单页 OCR
# ============================================================

def ocr_single_page(page, page_num: int) -> str:
    """对单个 pdfplumber 页面执行 OCR（复用全局 PaddleOCR 实例）"""
    import numpy as np
    try:
        ocr = get_ocr()
        img = page.to_image(resolution=PDF_RESOLUTION)
        img_array = np.array(img.original)
        result = ocr.ocr(img_array)
        if result and result[0]:
            lines = []
            for line_info in result[0]:
                if len(line_info) > 1 and len(line_info[1]) > 0:
                    text = line_info[1][0]
                    if text:
                        lines.append(text)
            return "\n".join(lines)
    except Exception as e:
        if "Ran out of memory" in str(e) or "OOM" in str(e).upper():
            print(f"    第{page_num}页: 显存/内存不足，跳过")
        else:
            print(f"    第{page_num}页 OCR 失败: {e}")
    return ""


# ============================================================
# 进度文件管理
# ============================================================

def load_progress(filepath: str) -> dict:
    """加载已完成的 OCR 进度"""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_progress(filepath: str, progress: dict):
    """持久化 OCR 进度"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def book_key(subject: str, filename: str) -> str:
    """生成进度文件中该书的键名"""
    return f"{subject}/{filename}"


# ============================================================
# 主处理逻辑
# ============================================================

def process_book(
    subject: str,
    filename: str,
    max_pages: int,
    book_index: int,
    total_books: int,
    progress: dict,
    progress_file: str,
) -> bool:
    """
    处理单本书：OCR → 清洗 → 分块 → 向量化入库

    返回 True 表示成功处理（或已跳过），False 表示文件缺失
    """
    import pdfplumber

    key = book_key(subject, filename)
    filepath = os.path.join(PDF_BASE, subject, filename)

    # ── 文件检查 ──
    if not os.path.exists(filepath):
        print(f"[{book_index}/{total_books}] MISS  {key}  (文件不存在)")
        return False

    # ── 已处理 → 跳过 ──
    if key in progress and progress[key].get("status") in ("done", "partial"):
        prev = progress[key]
        print(f"[{book_index}/{total_books}] SKIP {key}  (已完成: {prev.get('pages')}页, {prev.get('chunks')}块, {prev.get('time')}s)")
        return True

    t_start = time.time()
    label = f"[{book_index}/{total_books}]"
    print(f"\n{label} START {key}")
    print(f"  OCR 前 {max_pages} 页（扫描版，PaddleOCR）...")

    # ── OCR 逐页识别 ──
    pages_text: list[str] = []
    failed_pages = 0
    try:
        with pdfplumber.open(filepath) as pdf:
            total_pdf_pages = len(pdf.pages)
            pages_to_ocr = min(max_pages, total_pdf_pages)
            print(f"  PDF 共 {total_pdf_pages} 页，本次处理前 {pages_to_ocr} 页")

            for i in range(pages_to_ocr):
                page = pdf.pages[i]
                page_num = i + 1

                try:
                    page_text = ocr_single_page(page, page_num)
                except Exception:
                    page_text = ""

                if page_text:
                    pages_text.append(page_text)
                else:
                    failed_pages += 1

                # 进度打印
                if (page_num % 10 == 0) or (page_num == pages_to_ocr):
                    pct = page_num * 100 // pages_to_ocr
                    elapsed = time.time() - t_start
                    print(f"  {label} {filename[:20]} page {page_num}/{pages_to_ocr} ({pct}%) "
                          f"elapsed={elapsed:.0f}s", flush=True)

    except Exception as e:
        print(f"  {label} PDF 打开/处理失败: {e}")
        return False

    if not pages_text:
        print(f"  {label} OCR 结果为空（{failed_pages}页识别失败）")
        progress[key] = {"status": "empty", "pages": 0, "chunks": 0, "time": int(time.time() - t_start)}
        save_progress(progress_file, progress)
        return True

    print(f"  {label} OCR 完成: {len(pages_text)}/{pages_to_ocr} 页有内容（{failed_pages}页空白/失败）")

    # ── 清洗 ──
    t_clean = time.time()
    full_text = clean_ocr_text(pages_text)
    if not full_text:
        print(f"  {label} 清洗后无有效内容")
        progress[key] = {"status": "empty", "pages": len(pages_text), "chunks": 0, "time": int(time.time() - t_start)}
        save_progress(progress_file, progress)
        return True
    print(f"  {label} 清洗完成: {len(full_text)} 字符 ({time.time() - t_clean:.1f}s)")

    # ── 分块 ──
    chunks = chunk_text(full_text)
    title = filename.rsplit(".", 1)[0]
    print(f"  {label} 分块: {len(chunks)} 块 (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")

    # ── 向量化入库 ──（耗时，需要加载 BGE-M3）
    from app.services.rag_service import _embed, ingest_document

    ok_count = 0
    err_count = 0
    t_embed = time.time()
    for i, chunk_text_content in enumerate(chunks):
        try:
            emb = _embed([chunk_text_content])[0]
            ingest_document(
                content=chunk_text_content,
                title=title,
                source=key,
                doc_id=f"ocr:{subject}:{title}:chunk{i}",
            )
            ok_count += 1
            if (i + 1) % 20 == 0:
                print(f"  {label} 入库进度 {i + 1}/{len(chunks)}", flush=True)
        except Exception as e:
            err_count += 1
            print(f"  {label} chunk[{i}] 入库失败: {e}")

    # ── 记录进度 ──
    elapsed_total = int(time.time() - t_start)
    elapsed_embed = time.time() - t_embed
    progress[key] = {
        "status": "done",
        "pages": len(pages_text),
        "chunks": ok_count,
        "time": elapsed_total,
        "total_pdf_pages": pages_to_ocr,
    }
    save_progress(progress_file, progress)

    print(f"  {label} DONE: {ok_count}/{len(chunks)} chunks, "
          f"OCR={time.time() - t_start - elapsed_embed:.0f}s, "
          f"Embed={elapsed_embed:.0f}s, "
          f"Total={elapsed_total}s",
          flush=True)
    return True


# ============================================================
# CLI 入口
# ============================================================

def main():
    # 声明全局变量，允许 CLI 覆盖模块级常量
    global CHUNK_SIZE, CHUNK_OVERLAP, MAX_CHUNKS_PER_BOOK, PDF_RESOLUTION

    parser = argparse.ArgumentParser(
        description="批量 OCR 扫描版 PDF → 向量化入库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python app/scripts/batch_ingest_ocr.py --max-pages 100 --books 5
  python app/scripts/batch_ingest_ocr.py --max-pages 50 --books 2 --start-from 3
  python app/scripts/batch_ingest_ocr.py --max-pages 150 --books 1  # 单本深入
        """,
    )
    parser.add_argument(
        "--max-pages", type=int, default=100,
        help="每本书最多 OCR 多少页（默认 100）"
    )
    parser.add_argument(
        "--books", type=int, default=len(PRIORITY_OCR),
        help=f"本次处理几本书（默认全部 {len(PRIORITY_OCR)} 本）"
    )
    parser.add_argument(
        "--start-from", type=int, default=1,
        help="从书单第几本开始（默认 1，用于断点续跑）"
    )
    parser.add_argument(
        "--chunk-size", type=int, default=CHUNK_SIZE,
        help=f"分块大小（默认 {CHUNK_SIZE}）"
    )
    parser.add_argument(
        "--chunk-overlap", type=int, default=CHUNK_OVERLAP,
        help=f"分块重叠（默认 {CHUNK_OVERLAP}）"
    )
    parser.add_argument(
        "--max-chunks", type=int, default=MAX_CHUNKS_PER_BOOK,
        help=f"每本书最多入库块数（默认 {MAX_CHUNKS_PER_BOOK}）"
    )
    parser.add_argument(
        "--resolution", type=int, default=PDF_RESOLUTION,
        help=f"OCR DPI 分辨率（默认 {PDF_RESOLUTION}，越高越准越慢）"
    )
    parser.add_argument(
        "--progress-file", type=str,
        default=os.path.join(os.path.dirname(__file__), "..", "..", "ocr_ingest_done.json"),
        help="进度文件路径"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅列出将处理的文件，不实际执行 OCR"
    )

    args = parser.parse_args()

    # 更新全局配置
    CHUNK_SIZE = args.chunk_size
    CHUNK_OVERLAP = args.chunk_overlap
    MAX_CHUNKS_PER_BOOK = args.max_chunks
    PDF_RESOLUTION = args.resolution

    progress_file = os.path.abspath(args.progress_file)

    # 选取书单子集
    start_idx = args.start_from - 1
    end_idx = min(start_idx + args.books, len(PRIORITY_OCR))
    selected_books = PRIORITY_OCR[start_idx:end_idx]

    if not selected_books:
        print("错误: 书单为空，请检查 --start-from / --books 参数")
        return

    print("=" * 60)
    print("批量 OCR 扫描版 PDF → 向量化入库")
    print("=" * 60)
    print(f"  书单范围: 第 {start_idx + 1}-{end_idx} 本 / 共 {len(PRIORITY_OCR)} 本")
    print(f"  每本最多: {args.max_pages} 页")
    print(f"  分块参数: size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}, max={MAX_CHUNKS_PER_BOOK}")
    print(f"  OCR 分辨率: {PDF_RESOLUTION} DPI")
    print(f"  进度文件:   {progress_file}")
    print()

    if args.dry_run:
        print("=== DRY RUN: 仅列出文件 ===")
        for i, (subj, fname) in enumerate(selected_books, 1):
            fpath = os.path.join(PDF_BASE, subj, fname)
            exists = os.path.exists(fpath)
            status = "OK" if exists else "MISSING"
            print(f"  [{i}/{len(selected_books)}] {status:7s}  {subj}/{fname}")
        return

    # 加载进度
    progress = load_progress(progress_file)

    # 批处理
    total_start = time.time()
    success = 0
    skipped = 0
    missing = 0

    for i, (subject, filename) in enumerate(selected_books, 1):
        result = process_book(
            subject=subject,
            filename=filename,
            max_pages=args.max_pages,
            book_index=start_idx + i,
            total_books=len(PRIORITY_OCR),
            progress=progress,
            progress_file=progress_file,
        )

        # 检查是否跳过已完成的
        key = book_key(subject, filename)
        if key in progress and progress[key].get("status") in ("done", "partial"):
            skipped += 1
        elif result:
            success += 1
        else:
            missing += 1

        # 每本书之间稍微休息，避免 GPU 过热
        if i < len(selected_books):
            time.sleep(1)

    # ── 最终汇报 ──
    total_elapsed = time.time() - total_start
    print()
    print("=" * 60)
    print(f"批量 OCR 完成")
    print(f"  成功: {success}  跳过: {skipped}  缺失: {missing}")
    print(f"  总耗时: {total_elapsed:.0f}s ({total_elapsed / 60:.1f}min)")

    # 打印进度摘要
    progress = load_progress(progress_file)
    if progress:
        done_keys = [k for k, v in progress.items() if v.get("status") == "done"]
        total_chunks = sum(v.get("chunks", 0) for v in progress.values())
        print(f"  累计完成: {len(done_keys)} 本书, {total_chunks} chunks 已入库")

    from app.services.rag_service import get_knowledge_count
    print(f"  知识库总量: {get_knowledge_count()} 条")


if __name__ == "__main__":
    main()
