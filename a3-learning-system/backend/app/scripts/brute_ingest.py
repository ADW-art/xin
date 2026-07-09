"""
暴力全量入库 — 每本书的每一页，不管质量，全部录入。
策略：pdfplumber快路 → Tesseract慢路 → 不跳过任何页面 → 全chunk入库
"""

import io, os, re, subprocess, sys, tempfile, time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PDF_BASE = "E:/code/github_clone/pdf-计算机专业资源/Some-Many-Books/PDF-file"
MATERIALS = os.path.join(os.path.dirname(__file__), "knowledge_materials")
DONE = os.path.join(os.path.dirname(__file__), "..", "..", "brute_done.txt")
TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def get_page_text(page):
    """Get text from a page by ANY means"""
    # Fast: pdfplumber
    try:
        t = page.extract_text()
        if t and len(t.strip()) > 10:
            return t.strip()
    except:
        pass
    # Slow: Tesseract OCR
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
                text = fp.read().strip()
            os.unlink(txt)
            return text
    except:
        pass
    return ""


def ingest(book_key, title, text_chunks):
    """Write chunks to ChromaDB"""
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

    total = 0
    batch = 100
    for i in range(0, len(text_chunks), batch):
        b = text_chunks[i:i + batch]
        ids = [f"full:{title}:{i + j}" for j in range(len(b))]
        metas = [{"title": title, "source": book_key, "chunk": i + j} for j in range(len(b))]
        try:
            col.add(documents=b, embeddings=[[0.0] * 1024] * len(b), metadatas=metas, ids=ids)
            total += len(b)
        except:
            for j, c in enumerate(b):
                try:
                    col.add(documents=[c], embeddings=[[0.0] * 1024],
                            metadatas=[metas[j]], ids=[ids[j]])
                    total += 1
                except:
                    pass
    return total


# ── Main ──
already = set()
if os.path.exists(DONE):
    with open(DONE, "r", encoding="utf-8") as f:
        already = set(l.strip() for l in f)

# Gather ALL PDFs
todo = []
for root, dirs, files in os.walk(PDF_BASE):
    subj = Path(root).name
    for fn in sorted(files):
        if not fn.lower().endswith(".pdf"): continue
        key = f"{subj}/{fn}"
        if key not in already:
            todo.append((subj, fn, os.path.join(root, fn), key))
for fn in sorted(os.listdir(MATERIALS)):
    if not fn.lower().endswith(".pdf"): continue
    key = f"materials/{fn}"
    if key not in already:
        todo.append(("materials", fn, os.path.join(MATERIALS, fn), key))

print(f"待处理: {len(todo)} 本")
start_t = time.time()
total_chunks = 0

for idx, (subj, fn, path, key) in enumerate(todo):
    t0 = time.time()
    title = fn.rsplit(".", 1)[0][:80]
    print(f"[{idx + 1}/{len(todo)}] {subj}/{fn[:50]}", end=" ", flush=True)

    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = []
            fast = 0
            slow = 0
            for i, page in enumerate(pdf.pages):
                text = get_page_text(page)
                if text:
                    pages.append(text)
            full = "\n\n".join(pages)

            # Chunk all
            chunks = []
            pos = 0
            while pos < len(full):
                end = min(pos + 800, len(full))
                c = full[pos:end].strip()
                if c:
                    chunks.append(c)
                pos += 680

            # Ingest
            if chunks:
                n = ingest(key, title, chunks)
                total_chunks += n
                elapsed = time.time() - t0
                rate = (idx + 1) / max(time.time() - start_t, 1) * 3600
                print(f"→ {len(pages)}p {n}c {elapsed:.0f}s ({rate:.0f}/h)")
            else:
                print(f"→ EMPTY")

            with open(DONE, "a", encoding="utf-8") as f:
                f.write(key + "\n")

    except Exception as e:
        print(f"→ FAIL: {str(e)[:60]}")
        with open(DONE, "a", encoding="utf-8") as f:
            f.write(key + " ❌\n")

# Final stats
from chromadb import PersistentClient
from chromadb.config import Settings
client = PersistentClient(
    path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "chroma_data_local")),
    settings=Settings(anonymized_telemetry=False),
)
kb = client.get_collection("knowledge_base").count()
t = time.time() - start_t
print(f"\n{'=' * 50}")
print(f"完成: {len(todo)} 本 | {total_chunks} chunks | KB: {kb} | {t:.0f}s")
