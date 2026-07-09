"""
统一知识库入库脚本 — 覆盖 knowledge_materials/ 全部 PDF

特性:
  - 自动判断文字版/扫描版（pdfplumber 先试，空内容降级 PaddleOCR）
  - 滑动窗口分块 (800字符 + 120重叠)
  - BGE-M3 向量化 + ChromaDB + FAISS 双写
  - JSON 进度文件断点续传
  - 已入库 PDF 自动跳过

用法:
  python unified_ingest.py --dry-run          # 预览待处理 PDF
  python unified_ingest.py                    # 全部入库（断点续传）
  python unified_ingest.py --pdf "Redis设计与实现"  # 指定单本
  python unified_ingest.py --max-pages 50     # 扫描版每本最多 OCR 50 页
  python unified_ingest.py --max-chunks 150   # 每本最多 150 个 chunk
"""
import io, sys, os, time, json, re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.document_parser import parse_pdf
from app.services.rag_service import _embed, get_knowledge_count

MATERIALS_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_materials')
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), 'unified_ingest_progress.json')

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
DEFAULT_MAX_CHUNKS = 200
DEFAULT_MAX_PAGES_OCR = 80
MIN_CHUNK_LEN = 30


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_progress(progress):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def get_all_pdfs():
    """扫描 knowledge_materials 目录下所有 PDF"""
    if not os.path.exists(MATERIALS_DIR):
        print(f"[ERROR] 目录不存在: {MATERIALS_DIR}")
        return []
    files = []
    for f in sorted(os.listdir(MATERIALS_DIR)):
        if f.lower().endswith('.pdf'):
            files.append(f)
    return files


def get_ingested_pdfs():
    """从 ChromaDB 查询已入库的 PDF 文件名"""
    try:
        from app.core.chroma_client import get_collection
        col = get_collection('knowledge_base')
        r = col.get(limit=50000, include=['metadatas'])
        sources = set()
        if r and r.get('metadatas'):
            for m in r['metadatas']:
                if m:
                    src = m.get('source', '')
                    sources.add(src)
        return sources
    except Exception as e:
        print(f"[WARN] 无法查询 ChromaDB: {e}")
        return set()


def is_pdf_ingested(pdf_filename, chroma_sources):
    """检查 PDF 是否已在 ChromaDB 中"""
    pdf_stem = pdf_filename.replace('.pdf', '')
    # 用文件名前 40 字符做模糊匹配
    key = pdf_stem[:40]
    for src in chroma_sources:
        if key in src:
            return True
    return False


def chunk_text(text, max_chunks=DEFAULT_MAX_CHUNKS):
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < max_chunks:
        end = start + CHUNK_SIZE
        c = text[start:end].strip()
        if c and len(c) > MIN_CHUNK_LEN:
            chunks.append(c)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def extract_pdf_text(pdf_path, use_ocr=True, max_pages=DEFAULT_MAX_PAGES_OCR):
    """提取 PDF 文本：先 pdfplumber，失败则 OCR（限 max_pages 页）"""
    t0 = time.time()

    # 第一阶段：pdfplumber 直接提取
    try:
        paras = parse_pdf(pdf_path, use_ocr=False)
        cleaned = [p['content'].strip() for p in paras if len(p['content'].strip()) > 20]
        full = '\n\n'.join(cleaned)
        if len(full) > 500:  # 足够内容才信任文字提取
            elapsed = time.time() - t0
            print(f"  [text] {len(cleaned)}段 / {len(full)}字 / {elapsed:.0f}s", flush=True)
            return full
        elif full:
            print(f"  [text-thin] 仅{len(full)}字，尝试 OCR...", flush=True)
    except Exception as e:
        print(f"  pdfplumber 失败: {e}", flush=True)

    # 第二阶段：OCR（仅当前 max_pages 页）
    if not use_ocr:
        return ""

    print(f"  pdfplumber 内容不足，启动 OCR（最多 {max_pages} 页）...", flush=True)

    # 尝试 PaddleOCR（GPU加速）→ EasyOCR → 放弃
    ocr_text = _try_paddleocr(pdf_path, max_pages, t0)
    if ocr_text:
        return ocr_text

    ocr_text = _try_easyocr(pdf_path, max_pages, t0)
    if ocr_text:
        return ocr_text

    return ""


def _try_paddleocr(pdf_path, max_pages, t0):
    try:
        from paddleocr import PaddleOCR
        import pdfplumber, numpy as np

        ocr = PaddleOCR(lang='ch')
        pages_text = []

        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            n = min(max_pages, total_pages)
            for i in range(n):
                try:
                    page = pdf.pages[i]
                    img = page.to_image(resolution=200)
                    img_array = np.array(img.original)
                    result = ocr.predict(img_array)
                    if isinstance(result, list):
                        for item in result:
                            texts = None
                            if isinstance(item, dict) and 'rec_texts' in item:
                                texts = item['rec_texts']
                            elif hasattr(item, 'get'):
                                texts = item.get('rec_texts', [])
                            if texts:
                                lines = [t for t in texts if t and len(t.strip()) > 1]
                                if lines:
                                    pages_text.append('\n'.join(lines))
                except Exception:
                    pass
                if (i + 1) % 15 == 0:
                    elapsed = time.time() - t0
                    print(f"    PaddleOCR {i+1}/{n}, {elapsed:.0f}s", flush=True)

        if pages_text:
            full = '\n\n'.join(pages_text)
            full = re.sub(r'\n{3,}', '\n\n', full)
            full = re.sub(r'\s{2,}', ' ', full)
            elapsed = time.time() - t0
            print(f"  [paddleocr] {len(pages_text)}页/{len(full)}字/{elapsed:.0f}s", flush=True)
            return full
    except ImportError:
        pass
    except Exception as e:
        print(f"  PaddleOCR 失败: {e}", flush=True)
    return ""


def _try_easyocr(pdf_path, max_pages, t0):
    try:
        import easyocr
        import pdfplumber, numpy as np

        reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        pages_text = []

        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            n = min(max_pages, total_pages)
            for i in range(n):
                try:
                    page = pdf.pages[i]
                    img = page.to_image(resolution=150)
                    img_array = np.array(img.original)
                    result = reader.readtext(img_array)
                    lines = [item[1] for item in result if item[1] and len(item[1].strip()) > 1]
                    if lines:
                        pages_text.append('\n'.join(lines))
                except Exception:
                    pass
                if (i + 1) % 10 == 0:
                    print(f"    EasyOCR {i+1}/{n}, {time.time()-t0:.0f}s", flush=True)

        if pages_text:
            full = '\n\n'.join(pages_text)
            full = re.sub(r'\n{3,}', '\n\n', full)
            full = re.sub(r'\s{2,}', ' ', full)
            print(f"  [easyocr] {len(pages_text)}页/{len(full)}字/{time.time()-t0:.0f}s", flush=True)
            return full
    except ImportError:
        print(f"  EasyOCR 未安装", flush=True)
    except Exception as e:
        print(f"  EasyOCR 失败: {e}", flush=True)
    return ""


def process_pdf(filename, max_pages=DEFAULT_MAX_PAGES_OCR, max_chunks=DEFAULT_MAX_CHUNKS, use_ocr=True):
    """处理单个 PDF：提取 → 分块 → 批量向量化 → 双写"""
    pdf_path = os.path.join(MATERIALS_DIR, filename)
    if not os.path.exists(pdf_path):
        print(f"  [MISS] 文件不存在: {pdf_path}")
        return False

    title = filename.replace('.pdf', '')[:80]
    source = f"materials/{filename}"
    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"  [{title}]")
    print(f"{'='*60}", flush=True)

    # 1. 提取文本
    full_text = extract_pdf_text(pdf_path, use_ocr=use_ocr, max_pages=max_pages)
    if not full_text:
        print(f"  [FAIL] 无法提取文本", flush=True)
        return False

    # 2. 分块
    chunks = chunk_text(full_text, max_chunks=max_chunks)
    print(f"  分块: {len(chunks)} chunks", flush=True)

    if not chunks:
        print(f"  [FAIL] 无有效 chunk", flush=True)
        return False

    # 3. 批量向量化（比逐条调用快 2-3x）
    print(f"  向量化中...", flush=True)
    t_emb = time.time()
    try:
        embeddings = _embed(chunks)
    except Exception as e:
        print(f"  [FAIL] 向量化失败: {e}", flush=True)
        return False
    print(f"  向量化完成: {len(embeddings)} 条, {time.time()-t_emb:.0f}s", flush=True)

    # 4. 逐条双写 ChromaDB + FAISS
    from app.core.chroma_client import add_to_collection
    from app.services.faiss_client import get_faiss
    COLLECTION_NAME = "knowledge_base"

    mgr = get_faiss()
    idx_name = mgr.route(source)
    ok = 0

    for i, (c, emb) in enumerate(zip(chunks, embeddings)):
        try:
            doc_id = f"materials:{title}:chunk{i}"
            meta = {"title": title, "source": source}

            # ChromaDB
            add_to_collection(
                name=COLLECTION_NAME,
                documents=[c],
                metadatas=[meta],
                ids=[doc_id],
                embeddings=[emb],
            )

            # FAISS
            try:
                mgr.upsert(idx_name, [emb], [c], [meta])
            except Exception:
                pass

            ok += 1
            if (i + 1) % 50 == 0:
                elapsed = time.time() - t0
                print(f"    chunk {i+1}/{len(chunks)} ({elapsed:.0f}s)", flush=True)
        except Exception as e:
            print(f"    chunk[{i}] ERR: {e}", flush=True)

    elapsed = time.time() - t0
    print(f"  [DONE] {ok}/{len(chunks)} chunks, {elapsed:.0f}s, 知识库总量: {get_knowledge_count()}", flush=True)
    return ok > 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description='统一知识库入库')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际入库')
    parser.add_argument('--pdf', type=str, help='指定单本 PDF 文件名（模糊匹配）')
    parser.add_argument('--max-pages', type=int, default=DEFAULT_MAX_PAGES_OCR, help='扫描版每本最多 OCR 页数')
    parser.add_argument('--max-chunks', type=int, default=DEFAULT_MAX_CHUNKS, help='每本最多 chunk 数')
    parser.add_argument('--no-ocr', action='store_true', help='跳过 OCR，仅处理文字版 PDF')
    parser.add_argument('--force', action='store_true', help='强制重新入库（忽略已入库标记）')
    parser.add_argument('--start-from', type=str, help='从指定 PDF 开始处理')
    args = parser.parse_args()

    # 获取 PDF 列表
    all_pdfs = get_all_pdfs()
    print(f"knowledge_materials/ 共 {len(all_pdfs)} 本 PDF")

    # 获取已入库 PDF
    chroma_sources = get_ingested_pdfs()
    print(f"ChromaDB 已有 {len(chroma_sources)} 个来源")

    # 筛选待处理 PDF
    if args.pdf:
        # 模糊匹配指定 PDF
        targets = [f for f in all_pdfs if args.pdf[:20] in f]
        if not targets:
            print(f"[ERROR] 未找到匹配 PDF: {args.pdf}")
            print(f"  可用 PDF 列表:")
            for f in all_pdfs:
                print(f"    {f[:100]}")
            return
        print(f"  匹配到 {len(targets)} 本:")
        for t in targets:
            print(f"    {t[:100]}")
    else:
        targets = all_pdfs

    # 过滤已入库
    progress = load_progress()
    pending = []
    skipped = 0

    for pdf in targets:
        if args.force:
            pending.append(pdf)
            continue
        if progress.get(pdf) == 'done':
            skipped += 1
            continue
        if is_pdf_ingested(pdf, chroma_sources):
            progress[pdf] = 'done'
            skipped += 1
            continue
        pending.append(pdf)

    save_progress(progress)

    print(f"\n结果: {len(pending)} 本待处理, {skipped} 本已跳过")

    if args.dry_run:
        print(f"\n=== 待入库 PDF ({len(pending)}) ===")
        for i, pdf in enumerate(pending, 1):
            print(f"  {i:2d}. {pdf[:100]}")
        return

    if not pending:
        print("没有待处理的 PDF，知识库已完整。")
        return

    # 处理
    start_from = args.start_from
    started = start_from is None  # 如果没指定 start_from，从第一个开始

    for i, pdf in enumerate(pending):
        if not started:
            if start_from in pdf:
                started = True
            else:
                print(f"  SKIP {pdf[:80]} (start_from={start_from})")
                continue

        print(f"\n[{i+1}/{len(pending)}]", flush=True)
        success = process_pdf(
            pdf,
            max_pages=args.max_pages,
            max_chunks=args.max_chunks,
            use_ocr=not args.no_ocr,
        )
        if success:
            progress[pdf] = 'done'
            save_progress(progress)
        else:
            progress[pdf] = 'failed'
            save_progress(progress)

    print(f"\n{'='*60}")
    print(f"入库完成。知识库总量: {get_knowledge_count()} 条")
    print(f"进度文件: {PROGRESS_FILE}")


if __name__ == '__main__':
    main()
