"""
知识库批量入库脚本

支持:
  Markdown 文件 (knowledge_materials/*.md)  → 直接入库
  PDF 教材 (本地目录)                        → 解析 → 分chunk → 向量化 → 入库
  JSON 题库 (knowledge_materials/exercise_bank.json) → 导入 exercise_bank 集合

用法:
  # 导入 Markdown 教材 (已有)
  python -m app.scripts.ingest_knowledge --md

  # 扫描 PDF 目录: 检测哪些可解析 (必须第一步)
  python -m app.scripts.ingest_knowledge --scan

  # 批量入库 PDF (扫描后执行)
  python -m app.scripts.ingest_knowledge --pdf

  # 指定学科: --subject python,algorithms,mysql
  python -m app.scripts.ingest_knowledge --pdf --subject algorithms

  # 导入题库
  python -m app.scripts.ingest_knowledge --exercises

  # 查询知识库状态
  python -m app.scripts.ingest_knowledge --status

  # 全部流程: MD + PDF扫描 + PDF入库 + 题库
  python -m app.scripts.ingest_knowledge --all
"""

import argparse
import io
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows 终端 UTF-8 编码修复
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest")

# 教材 PDF 根目录
PDF_BASE = "E:/code/github_clone/pdf-计算机专业资源/Some-Many-Books/PDF-file"

# 知识素材目录 (Markdown + 题库)
MATERIALS_DIR = os.path.join(os.path.dirname(__file__), "knowledge_materials")

# 进度文件 (断点续传)
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "ingest_progress.json")

# Chunk 参数
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS_PER_BOOK = 150


# ═══════════════════════════════════════════════════════════════
# Markdown 导入
# ═══════════════════════════════════════════════════════════════

def ingest_markdown_files():
    """导入 knowledge_materials 目录下的所有 .md 文件"""
    from app.services.rag_service import ingest_document, get_knowledge_count

    if not os.path.isdir(MATERIALS_DIR):
        logger.warning("知识素材目录不存在: %s", MATERIALS_DIR)
        return

    files = sorted([f for f in os.listdir(MATERIALS_DIR) if f.endswith(".md")])
    logger.info("发现 %d 个 Markdown 文件", len(files))

    for fname in files:
        fpath = os.path.join(MATERIALS_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        title = fname.replace(".md", "")
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                title = line[2:].strip()
                break

        try:
            doc_id = ingest_document(title=title, content=content,
                                     source=f"Python官方文档/{fname}")
            logger.info("  MD入库: %s → %s", fname, doc_id)
        except Exception as e:
            logger.warning("  MD入库失败 %s: %s", fname, e)

    logger.info("MD导入完成, 知识库总计 %d 条", get_knowledge_count())


# ═══════════════════════════════════════════════════════════════
# PDF 扫描
# ═══════════════════════════════════════════════════════════════

def quick_scan_pdf(path: str, pages: int = 3) -> dict:
    """快速检测 PDF 前 N 页是否有可提取文字"""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:pages]:
                t = page.extract_text()
                if t:
                    text += t + "\n"
        return {"text_len": len(text.strip()), "error": None}
    except Exception as e:
        return {"text_len": 0, "error": str(e)[:100]}


def scan_pdfs(subjects: list[str] = None):
    """扫描全部 PDF，分类输出可入库/扫描版/损坏"""
    results = []
    total = 0
    for root, dirs, files in os.walk(PDF_BASE):
        subject = Path(root).name
        if subjects and subject not in subjects:
            continue
        for f in sorted(files):
            if not f.lower().endswith('.pdf'):
                continue
            total += 1
            path = os.path.join(root, f)
            r = quick_scan_pdf(path)
            r["subject"] = subject
            r["filename"] = f
            r["path"] = path
            results.append(r)

    text_ok = sorted([r for r in results if r["text_len"] > 100], key=lambda x: -x["text_len"])
    scanned = [r for r in results if r["text_len"] == 0 and not r["error"]]
    errored = [r for r in results if r["error"]]

    print("\n" + "=" * 70)
    print(f"  扫描完成: {total} 本")
    print(f"  [OK] 可入库: {len(text_ok)} 本 (文字层 >=100字)")
    print(f"  [OCR] 扫描版: {len(scanned)} 本 (需 OCR)")
    print(f"  [ERR] 错误:   {len(errored)} 本")
    print("=" * 70)

    print(f"\n--- 可入库 Top-50 (按字数) ---")
    for r in text_ok[:50]:
        bar = "#" * min(40, r["text_len"] // 500)
        print(f"  {r['text_len']:>7}字 {bar} [{r['subject']:>16}] {r['filename'][:55]}")

    if scanned:
        print(f"\n--- 扫描版 (需OCR, {len(scanned)}本) ---")
        for r in scanned:
            print(f"  [{r['subject']:>16}] {r['filename'][:60]}")

    if errored:
        print(f"\n--- 解析错误 ({len(errored)}本) ---")
        for r in errored:
            print(f"  [{r['subject']:>16}] {r['filename'][:50]}: {r['error']}")

    # 保存
    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "scan_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "scanned_at": datetime.now().isoformat(),
            "total": total, "text_ok": len(text_ok),
            "scanned_need_ocr": len(scanned), "errored": len(errored),
            "books": [{"subject": r["subject"], "filename": r["filename"],
                        "text_len": r["text_len"], "error": r["error"]}
                      for r in results],
        }, f, ensure_ascii=False, indent=2)
    logger.info("扫描结果: %s", out_path)


# ═══════════════════════════════════════════════════════════════
# PDF 入库
# ═══════════════════════════════════════════════════════════════

def chunk_text(text: str) -> list[str]:
    """滑动窗口分块"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
        if len(chunks) >= MAX_CHUNKS_PER_BOOK:
            break
    return chunks


def parse_full_pdf(path: str) -> list[str]:
    """解析 PDF → 清洗后的段落列表"""
    from app.services.document_parser import parse_pdf
    paragraphs = parse_pdf(path, use_ocr=False)
    if not paragraphs:
        return []

    skip_kw = ["图灵社区会员", "仅供学习交流", "版权所", "试读章节",
               "更多电子书", "扫描关注", "公众号", "微信", "QQ群"]
    cleaned = []
    for p in paragraphs:
        content = p["content"].strip()
        if len(content) < 15:
            continue
        if any(s in content for s in skip_kw):
            continue
        # 去 pdfplumber 常见噪声
        if content.count(" ") > len(content) * 0.4:  # 空格占比过高 → 表格/乱码
            continue
        cleaned.append(content)
    return cleaned


def load_progress() -> set:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f).get("done", []))
    return set()


def save_progress(done: set):
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({"done": list(done), "updated": datetime.now().isoformat()},
                  f, ensure_ascii=False)


def ingest_pdfs(subjects: list[str] = None):
    """批量入库 PDF 教材"""
    from app.services.rag_service import _embed, ingest_document

    done = load_progress()
    logger.info("断点续传: 已入库 %d 本", len(done))

    # 收集所有待处理 PDF
    todo = []
    for root, dirs, files in os.walk(PDF_BASE):
        subject = Path(root).name
        if subjects and subject not in subjects:
            continue
        for f in sorted(files):
            if not f.lower().endswith('.pdf'):
                continue
            path = os.path.join(root, f)
            key = f"{subject}/{f}"
            if key not in done:
                todo.append((subject, f, path, key))

    logger.info("待入库: %d 本", len(todo))

    for idx, (subject, filename, path, key) in enumerate(todo):
        logger.info("[%d/%d] %s/%s", idx + 1, len(todo), subject, filename[:50])

        # 预检
        scan = quick_scan_pdf(path, pages=2)
        if scan["text_len"] < 100:
            logger.warning("  跳过 (文字太少: %d字)", scan["text_len"])
            done.add(key)
            save_progress(done)
            continue

        # 解析
        t0 = time.time()
        try:
            paragraphs = parse_full_pdf(path)
        except Exception as e:
            logger.error("  解析失败: %s", e)
            done.add(key)
            save_progress(done)
            continue

        if not paragraphs:
            logger.warning("  跳过 (无有效段落)")
            done.add(key)
            save_progress(done)
            continue

        full_text = "\n\n".join(paragraphs)
        chunks = chunk_text(full_text)
        title = filename.rsplit(".", 1)[0]

        # 向量化 + 入库
        success = 0
        for i, chunk in enumerate(chunks):
            try:
                embedding = _embed([chunk])[0]
                ingest_document(
                    content=chunk,
                    title=title,
                    source=f"{subject}/{filename}",
                    doc_id=f"{subject}:{title}:chunk{i}",
                )
                success += 1
            except Exception as e:
                logger.warning("  chunk %d/%d 失败: %s", i + 1, len(chunks), e)

        elapsed = time.time() - t0
        logger.info("  ✅ %d/%d chunks, %.1fs, %.1f字",
                    success, len(chunks), elapsed, len(full_text))
        done.add(key)
        save_progress(done)


# ═══════════════════════════════════════════════════════════════
# 题库导入
# ═══════════════════════════════════════════════════════════════

def ingest_exercises():
    """导入题库 JSON → exercise_bank 集合"""
    from app.services.rag_service import load_exercise_bank

    path = os.path.join(MATERIALS_DIR, "exercise_bank.json")
    if not os.path.exists(path):
        logger.warning("题库文件不存在: %s", path)
        return
    n = load_exercise_bank(path)
    logger.info("题库导入完成: %d 题", n)


# ═══════════════════════════════════════════════════════════════
# 状态查询
# ═══════════════════════════════════════════════════════════════

def show_status():
    """显示知识库当前状态"""
    from app.services.rag_service import get_knowledge_count
    from app.core.chroma_client import get_collection

    kb_count = get_knowledge_count()

    try:
        ex_col = get_collection("exercise_bank")
        ex_r = ex_col.get()
        ex_count = len(ex_r["ids"]) if ex_r and ex_r.get("ids") else 0
    except Exception:
        ex_count = 0

    # 进度
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            pdata = json.load(f)
        pdf_done = len(pdata.get("done", []))
    else:
        pdf_done = 0

    # FAISS 状态
    try:
        from app.services.faiss_client import get_faiss
        faiss_total = get_faiss().get_total()
    except Exception:
        faiss_total = 0

    print(f"""
╔═══════════════════════════════════════════════════════
║  知识库状态
╠═══════════════════════════════════════════════════════
║  ChromaDB knowledge_base : {kb_count:>6} 条
║  ChromaDB exercise_bank  : {ex_count:>6} 题
║  FAISS 向量总数          : {faiss_total:>6} 条
║  PDF 已入库 (进度文件)   : {pdf_done:>6} 本
╚═══════════════════════════════════════════════════════
""")


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A3 知识库批量入库工具")
    parser.add_argument("--md", action="store_true", help="导入 knowledge_materials/*.md")
    parser.add_argument("--scan", action="store_true", help="扫描 PDF 目录，检测可解析文件")
    parser.add_argument("--pdf", action="store_true", help="批量入库 PDF 教材")
    parser.add_argument("--exercises", action="store_true", help="导入题库 exercise_bank.json")
    parser.add_argument("--status", action="store_true", help="显示知识库状态")
    parser.add_argument("--all", action="store_true", help="全部执行: md + scan + pdf + exercises")
    parser.add_argument("--subject", type=str, default=None, help="指定学科目录 (逗号分隔)")
    parser.add_argument("--reset", action="store_true", help="清除进度文件，重新入库")
    args = parser.parse_args()

    if args.reset and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        logger.info("进度已重置")

    subs = [s.strip() for s in args.subject.split(",")] if args.subject else None

    if args.status:
        show_status()
    elif args.all:
        ingest_markdown_files()
        scan_pdfs(subs)
        ingest_pdfs(subs)
        ingest_exercises()
        show_status()
    elif args.md:
        ingest_markdown_files()
    elif args.scan:
        scan_pdfs(subs)
    elif args.pdf:
        ingest_pdfs(subs)
    elif args.exercises:
        ingest_exercises()
    else:
        parser.print_help()
