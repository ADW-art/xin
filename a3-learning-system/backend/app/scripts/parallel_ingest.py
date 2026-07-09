"""
并行入库：3进程同时OCR不同书本，3倍速度
"""
import json, os, sys, time
from multiprocessing import Process

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

MATERIALS = os.path.join(os.path.dirname(__file__), 'knowledge_materials')
PROGRESS = os.path.join(os.path.dirname(__file__), 'parallel_ingest_progress.json')

# 15 selected books
BOOKS = [
    "C++程序设计语言.第1～3部分.原书第4版 (Bjarne Stroustrup) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "Java核心技术·卷 II（原书第11版）：高级特性 (凯 S.霍斯特曼 (Cay S.Horstmann)) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "Python语言程序设计基础（第2版） (嵩天，礼欣，黄天羽 著) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "大话数据结构.pdf",
    "算法导论（原书第3版） (Thomas H.Cormen,Charles E.Leiserson etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "操作系统概念（原书第9版） ( etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "TCPIP详解 卷1：协议（原书第2版） (凯文 R. 福尔 (Kevin R. Fall) etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "数据库系统概念 原书第6版 本科教学版 (Silberschatz，Korth，Sudarshan著 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "人工智能：一种现代的方法（第3版） (罗素 诺维格) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "计算机科学丛书：编译原理（第2版） ([美]Alfred V.Aho, [美]Monica S.Lam etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "离散数学及其应用（原书第8版） (Kenneth H.Rosen) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "软件工程导论 (张海藩 牟永敏) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "计算机组成原理 (艾伦·克莱门茨 (Alan Clements)) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "分布式系统：概念与设计（原书第五版） ( etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    "GitHub入门与实践 (大塚弘记) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
]


def load_progress():
    if os.path.exists(PROGRESS):
        with open(PROGRESS, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_progress(p):
    with open(PROGRESS, 'w', encoding='utf-8') as f:
        json.dump(p, f, ensure_ascii=False, indent=2)


def process_book(filename):
    """Process a single book end-to-end, with crash resilience"""
    import re, pdfplumber, numpy as np
    from paddleocr import PaddleOCR
    from app.services.rag_service import _embed, get_knowledge_count
    from app.core.chroma_client import add_to_collection
    from app.services.faiss_client import get_faiss

    path = os.path.join(MATERIALS, filename)
    title = filename.replace('.pdf', '')[:80]
    source = f"materials/{filename}"
    t0 = time.time()

    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
        ocr = PaddleOCR(lang='ch')
        pages_text = []
        stuck = 0
        for i in range(total):
            ps = time.time()
            try:
                img = pdf.pages[i].to_image(resolution=120)
                arr = np.array(img.original)
                res = ocr.predict(arr)
                for item in res:
                    ts = item.get('rec_texts', []) if hasattr(item, 'get') else []
                    ls = [t for t in ts if t and len(t.strip()) > 1]
                    if ls: pages_text.append('\n'.join(ls))
            except: pass
            # If a single page took >180s, flag it
            if time.time() - ps > 180:
                stuck += 1
            if (i+1) % 50 == 0 or i == 0:
                el = time.time() - t0
                print(f"  [{title[:30]}] OCR {i+1}/{total} {el:.0f}s stuck:{stuck}", flush=True)

    if not pages_text:
        return False, "no text"

    raw = '\n\n'.join(pages_text)
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    raw = re.sub(r'\s{2,}', ' ', raw)

    # Chunk
    cks, start = [], 0
    while start < len(raw) and len(cks) < 300:
        end = start + 800
        c = raw[start:end].strip()
        if c and len(c) > 30: cks.append(c)
        start += 680

    # Embed
    print(f"  [{title[:30]}] embed {len(cks)} chunks...", flush=True)
    try:
        embs = _embed(cks)
    except Exception as e:
        print(f"  [{title[:30]}] embed failed: {e}, using zeros", flush=True)
        embs = [[0.0] * 1024 for _ in cks]

    # Write
    mgr = get_faiss()
    idx = mgr.route(source)
    ok = 0
    for i, (c, e) in enumerate(zip(cks, embs)):
        try:
            add_to_collection(name="knowledge_base", documents=[c],
                            metadatas=[{"title": title, "source": source}],
                            ids=[f"materials:{title}:chunk{i}"], embeddings=[e])
            try: mgr.upsert(idx, [e], [c], [{"title": title, "source": source}])
            except: pass
            ok += 1
        except: pass
    el = time.time() - t0
    print(f"  [{title[:30]}] DONE {ok} chunks {el:.0f}s KB:{get_knowledge_count()}", flush=True)
    return True, ""


def worker(book_list, worker_id):
    """Worker process: ingest a list of books"""
    pg = load_progress()
    for filename in book_list:
        if pg.get(filename) == 'done':
            print(f"[W{worker_id}] SKIP {filename[:50]}...", flush=True)
            continue
        print(f"\n[W{worker_id}] START {filename[:60]}", flush=True)
        ok, msg = process_book(filename)
        pg = load_progress()  # re-read in case another worker updated
        if ok:
            pg[filename] = 'done'
        else:
            pg[filename] = f'fail:{msg}'
        save_progress(pg)


def main():
    # Split books into 3 groups
    n_workers = 3
    groups = [[] for _ in range(n_workers)]
    for i, book in enumerate(BOOKS):
        groups[i % n_workers].append(book)

    for wi, g in enumerate(groups):
        pages = 0
        for b in g:
            for name, pgs in json.load(open(os.path.join(os.path.dirname(__file__), 'pdf_classification.json'), encoding='utf-8'))['scan']:
                if b == name: pages += pgs; break
        print(f"W{wi}: {len(g)} books, ~{pages} pages")
    print()

    procs = []
    for wi, g in enumerate(groups):
        p = Process(target=worker, args=(g, wi))
        p.start()
        procs.append(p)
        time.sleep(5)  # stagger starts

    for p in procs:
        p.join()

    print("\nAll workers done!")


if __name__ == '__main__':
    main()
