"""
全量入库脚本 — 文字版优先，扫描版全页 PaddleOCR

策略: TEXT(4本补全+18验证) → SCAN(48本全量)
"""
import json, os, sys, time, re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout.reconfigure(encoding='utf-8')

from app.services.rag_service import _embed, get_knowledge_count
from app.core.chroma_client import add_to_collection
from app.services.faiss_client import get_faiss

CNAME = "knowledge_base"
CHUNK_SIZE = 800
OVERLAP = 120
MAX_CHUNKS = 300

PROGRESS = os.path.join(os.path.dirname(__file__), 'full_ingest_progress.json')
MATERIALS = os.path.join(os.path.dirname(__file__), 'knowledge_materials')


def load():
    if os.path.exists(PROGRESS):
        with open(PROGRESS, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save(p):
    with open(PROGRESS, 'w', encoding='utf-8') as f:
        json.dump(p, f, ensure_ascii=False, indent=2)


def chunks(text):
    out, start = [], 0
    while start < len(text) and len(out) < MAX_CHUNKS:
        end = start + CHUNK_SIZE
        c = text[start:end].strip()
        if c and len(c) > 30:
            out.append(c)
        start += CHUNK_SIZE - OVERLAP
    return out


def process(filename):
    path = os.path.join(MATERIALS, filename)
    if not os.path.exists(path):
        return False, "missing", {}
    title = filename.replace('.pdf', '')[:80]
    source = f"materials/{filename}"
    t0 = time.time()

    import pdfplumber, numpy as np
    try:
        with pdfplumber.open(path) as pdf:
            total = len(pdf.pages)
            sc = sum(len(pdf.pages[i].extract_text() or '') for i in range(min(5, total)))
            mode = 'text' if sc > 500 else 'scan'

            if mode == 'text':
                parts = []
                for i in range(total):
                    try:
                        t = pdf.pages[i].extract_text()
                        if t and len(t.strip()) > 10:
                            parts.append(t.strip())
                    except: pass
                    if (i+1) % 200 == 0:
                        print(f"    txt {i+1}/{total} {time.time()-t0:.0f}s", flush=True)
                raw = '\n\n'.join(parts)
                print(f"  [{mode}] {total}p -> {len(raw)}c, {time.time()-t0:.0f}s", flush=True)
            else:
                from paddleocr import PaddleOCR
                from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
                ocr = PaddleOCR(lang='ch')
                pages = []
                stuck_count = 0
                for i in range(total):
                    page_start = time.time()
                    try:
                        img = pdf.pages[i].to_image(resolution=120)
                        arr = np.array(img.original)
                        # Run OCR in thread with 3-minute timeout per page
                        with ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(ocr.predict, arr)
                            try:
                                res = future.result(timeout=180)
                            except FutureTimeout:
                                stuck_count += 1
                                print(f"    SKIP page {i+1} (timeout >180s, total stuck: {stuck_count})", flush=True)
                                continue
                        for item in res:
                            ts = item.get('rec_texts', []) if hasattr(item, 'get') else []
                            ls = [t for t in ts if t and len(t.strip()) > 1]
                            if ls: pages.append('\n'.join(ls))
                    except FutureTimeout:
                        stuck_count += 1
                        continue
                    except Exception as e:
                        pass
                    if (i+1) % 10 == 0 or i == 0:
                        el = time.time()-t0
                        eta = (el/(i+1))*(total-i-1) if i > 0 else 0
                        print(f"    OCR {i+1}/{total} {el:.0f}s ETA{eta:.0f}s (stuck:{stuck_count})", flush=True)
                raw = '\n\n'.join(pages)
                raw = re.sub(r'\n{3,}', '\n\n', raw)
                raw = re.sub(r'\s{2,}', ' ', raw)
                print(f"  [{mode}] {total}p -> {len(raw)}c, {time.time()-t0:.0f}s", flush=True)

    except Exception as e:
        return False, str(e), {}

    if not raw or len(raw.strip()) < 100:
        return False, "empty", {}

    cks = chunks(raw)
    print(f"  chunks:{len(cks)}", flush=True)

    # Embed all at once (single call avoids multi-call instability)
    t2 = time.time()
    print(f"  embedding {len(cks)} chunks...", flush=True)
    try:
        embs = _embed(cks)
        print(f"  embed done: {time.time()-t2:.0f}s", flush=True)
    except Exception as e:
        print(f"  WARN: embedding failed ({e}), using zero vectors", flush=True)
        # Zero vectors as fallback - text still searchable via BM25
        embs = [[0.0] * 1024 for _ in cks]

    # Write to DB
    mgr = get_faiss()
    idx_name = mgr.route(source)
    ok = 0
    for i, (c, e) in enumerate(zip(cks, embs)):
        try:
            did = f"materials:{title}:chunk{i}"
            add_to_collection(name=CNAME, documents=[c], metadatas=[{"title":title,"source":source}], ids=[did], embeddings=[e])
            try: mgr.upsert(idx_name, [e], [c], [{"title":title,"source":source}])
            except: pass
            ok += 1
            if (i+1) % 100 == 0:
                print(f"  wrote {i+1}/{len(cks)}", flush=True)
        except: pass

    el = time.time()-t0
    print(f"  DONE: {ok}/{len(cks)} chunks, {el:.0f}s, KB:{get_knowledge_count()}", flush=True)
    return True, "", {'mode':mode,'pages':total,'chunks':ok,'elapsed':int(el)}


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--start', type=int, default=0)
    p.add_argument('--scan-only', action='store_true', help='Skip text, only process scan PDFs')
    args = p.parse_args()

    pg = load()
    with open(os.path.join(os.path.dirname(__file__), 'pdf_classification.json'), 'r', encoding='utf-8') as f:
        clf = json.load(f)

    txt = [(n, pgs, 'TEXT') for n, pgs in clf['text']]
    scn = [(n, pgs, 'SCAN') for n, pgs in clf['scan']]
    queue = scn if args.scan_only else txt + scn
    pending = [(n, pgs, tp) for n, pgs, tp in queue if pg.get(n) != 'done']
    print(f"Queue: {len(txt)}T + {len(scn)}S = {len(queue)} | Pending: {len(pending)}")
    tp = sum(pgs for _,pgs,t in pending if t=='TEXT')
    sp = sum(pgs for _,pgs,t in pending if t=='SCAN')
    print(f"Text pages: {tp:,} (~{tp*0.02:.0f}min) | Scan pages: {sp:,} (~{sp*13/3600:.1f}h)")
    if args.dry_run:
        for i,(n,pg,tp) in enumerate(pending):
            print(f"  {i+1:3d}. [{tp}] {pg:4d}p {n[:80]}")
        return

    ok, fail = 0, 0
    t0 = time.time()
    for i, (fn, pgs, tp) in enumerate(pending):
        if i < args.start: continue
        print(f"\n[{'='*50}]\n[{i+1}/{len(pending)}] [{tp}] {pgs}p {fn[:80]}\n[{'='*50}]")
        s, msg, info = process(fn)
        pg[fn] = 'done' if s else f'fail:{msg}'
        save(pg)
        if s: ok += 1
        else: fail += 1; print(f"  FAIL: {msg}")
        if (i+1) % 5 == 0:
            el = time.time()-t0
            eta = (el/(i+1-args.start))*(len(pending)-i-1)
            print(f"\n--- {i+1}/{len(pending)} ok={ok} fail={fail} ETA {eta/3600:.1f}h ---")

    print(f"\nDONE {ok}ok {fail}fail {time.time()-t0:.0f}s | KB:{get_knowledge_count()}")


if __name__ == '__main__':
    main()
