"""
永不崩溃的持续入库脚本。
逐本处理，出错跳过，断点续跑。
"""

import io, os, re, subprocess, sys, tempfile, time, traceback

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
DONE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "brute_done.txt")
CHUNK_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "ocr_output")

def ocr_page(page):
    try:
        t = page.extract_text()
        if t and len(t.strip()) > 10:
            return t.strip()
    except:
        pass
    try:
        from PIL import Image
        import numpy as np
        img = page.to_image(resolution=150)
        pil = Image.fromarray(np.array(img.original))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            pil.save(f.name)
        out = f.name.replace(".png", "")
        subprocess.run([TESS, f.name, out, "-l", "chi_sim+eng", "--psm", "6"],
                       capture_output=True, text=True, timeout=25)
        os.unlink(f.name)
        txt = out + ".txt"
        if os.path.exists(txt):
            with open(txt, "r", encoding="utf-8") as fp:
                result = fp.read().strip()
            os.unlink(txt)
            return result
    except:
        pass
    return ""

def process_book(subj, fname, path):
    import pdfplumber
    t0 = time.time()
    title = fname.rsplit(".", 1)[0][:80]
    pages_text = []

    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
        for i in range(total):
            text = ocr_page(pdf.pages[i])
            if text:
                pages_text.append(text)
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{total} pages ({time.time()-t0:.0f}s)", flush=True)

    if not pages_text:
        return None, 0

    full = "\n\n".join(pages_text)
    chunks = []
    pos = 0
    while pos < len(full):
        c = full[pos:min(pos + 800, len(full))].strip()
        if c:
            chunks.append(c)
        pos += 680

    # Save to ChromaDB
    from chromadb import PersistentClient
    from chromadb.config import Settings
    client = PersistentClient(
        path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "chroma_data_local")),
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        col = client.get_collection("knowledge_base")
    except:
        col = client.create_collection("knowledge_base")

    ingested = 0
    batch = 200
    for i in range(0, len(chunks), batch):
        b = chunks[i:i + batch]
        ids = [f"all:{title}:{i + j}" for j in range(len(b))]
        metas = [{"title": title, "source": f"{subj}/{fname}", "chunk": i + j} for j in range(len(b))]
        try:
            col.add(documents=b, embeddings=[[0.0] * 1024] * len(b), metadatas=metas, ids=ids)
            ingested += len(b)
        except:
            for j, c in enumerate(b):
                try:
                    col.add(documents=[c], embeddings=[[0.0] * 1024], metadatas=[metas[j]], ids=[ids[j]])
                    ingested += 1
                except:
                    pass

    elapsed = time.time() - t0
    print(f"  → {len(pages_text)}/{total}p {len(chunks)}c {elapsed:.0f}s ({ingested} ingested)", flush=True)
    return title, ingested


# ── MAIN ──
os.makedirs(CHUNK_DIR, exist_ok=True)

# Load remaining books
todo = []
with open("todo_remaining.txt", "r", encoding="utf-8") as f:
    for line in f:
        parts = line.strip().split("|")
        if len(parts) == 4:
            todo.append((parts[0], parts[1], parts[2], parts[3]))

# Filter already done
already = set()
if os.path.exists(DONE_FILE):
    with open(DONE_FILE, encoding="utf-8") as f:
        already = set(line.strip().split(" ")[0] for line in f if line.strip())
todo = [(s, fn, p, k) for s, fn, p, k in todo if k not in already]

print(f"Books to process: {len(todo)}")
start_all = time.time()
total_chunks = 0
errors = 0

for idx, (subj, fname, path, key) in enumerate(todo):
    print(f"\n[{idx+1}/{len(todo)}] {subj}/{fname[:60]}", flush=True)
    try:
        title, n = process_book(subj, fname, path)
        if title:
            total_chunks += n
            with open(DONE_FILE, "a", encoding="utf-8") as f:
                f.write(f"{key}\n")
        else:
            print(f"  → SKIP (no text)", flush=True)
            with open(DONE_FILE, "a", encoding="utf-8") as f:
                f.write(f"{key} EMPTY\n")
    except Exception as e:
        print(f"  → ERROR: {e}", flush=True)
        traceback.print_exc()
        with open(DONE_FILE, "a", encoding="utf-8") as f:
            f.write(f"{key} ERROR\n")
        errors += 1
        continue

    elapsed = time.time() - start_all
    rate = (idx + 1) / max(elapsed, 1) * 60
    print(f"  Progress: {idx+1}/{len(todo)} ({rate:.1f}/min) errors:{errors}", flush=True)

t = time.time() - start_all
from chromadb import PersistentClient
from chromadb.config import Settings
client = PersistentClient(
    path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "chroma_data_local")),
    settings=Settings(anonymized_telemetry=False),
)
kb = client.get_collection("knowledge_base").count()
print(f"\n{'='*50}")
print(f"DONE: {len(todo)} books | {total_chunks} chunks | KB:{kb} | {t:.0f}s ({t/3600:.1f}h) | {errors} errors")
