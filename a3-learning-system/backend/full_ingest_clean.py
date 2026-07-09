"""
补全 71 本项目书（只扫 knowledge_materials）—— APPEND 模式

· 只处理项目目录 app/scripts/knowledge_materials 下的 PDF
· 现有语料（含外部书、curated 等）一块不动 —— 纯追加
· 对"入库不足"(有效干净块 < KEEP_MIN)的项目书：全页 OCR + 乱码过滤 → 追加
· 已充分入库的书跳过；可断点续跑（_ingest_clean_done.txt）

运行（先停后端，单进程）：
  python full_ingest_clean.py
完成后（无需 del _emb.f32，reembed 会从现有进度续算）：
  python reembed.py BAAI/bge-large-zh-v1.5
  python rebuild_stores.py
"""
import io, os, re, sys, json, time, tempfile, subprocess, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pdfplumber
from PIL import Image
import numpy as np

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
MAT = "app/scripts/knowledge_materials"
MAIN = "_rebuild_source.jsonl"
DONE = "_ingest_clean_done.txt"
KEEP_MIN = 250  # 有效干净块 >= 此值视为已充分入库，跳过

cjk = re.compile(r"[一-鿿]")


def is_good(t: str) -> bool:
    ns = t.replace(" ", "").replace("\n", "").replace("\t", "")
    if len(ns) < 30:
        return False
    space_ratio = t.count(" ") / max(len(t), 1)
    ncjk = len(cjk.findall(ns))
    nalnum = sum(c.isalnum() and c.isascii() for c in ns)
    if ncjk > 20 and space_ratio > 0.28:      # 中文被 OCR 拆成单字
        return False
    if (ncjk + nalnum) / len(ns) < 0.55:       # 符号/噪声过多
        return False
    if t.count("混混藏书阁") > 1:              # 重复水印
        return False
    if t.count(".") > len(t) * 0.4:            # 目录引导点
        return False
    return True


def title_stem(src: str) -> str:
    b = os.path.basename(src).rsplit(".", 1)[0]
    return re.split(r"[（(]| \(z-library| =| 第| 原书| \(\d", b)[0].strip()[:16]


def ocr_page(page) -> str:
    try:
        x = page.extract_text()
        if x and len(x.strip()) > 20:
            return x.strip()
    except Exception:
        pass
    try:
        img = page.to_image(resolution=150)
        pil = Image.fromarray(np.array(img.original))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            pil.save(f.name)
        o = f.name[:-4]
        subprocess.run([TESS, f.name, o, "-l", "chi_sim+eng", "--psm", "6"],
                       capture_output=True, timeout=20)
        os.unlink(f.name)
        tf = o + ".txt"
        if os.path.exists(tf):
            r = open(tf, encoding="utf-8").read().strip()
            os.unlink(tf)
            return r
    except Exception:
        pass
    return ""


def chunks_of(full: str):
    return [full[s:s + 800].strip() for s in range(0, len(full), 680) if full[s:s + 800].strip()]


def main():
    # 统计现有每本项目书的干净块数（materials/ 键 + 标题 stem 取较大值）
    mat_clean = collections.Counter()
    stem_clean = collections.Counter()
    if os.path.exists(MAIN):
        with open(MAIN, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                s = (r.get("meta") or {}).get("source", "")
                if is_good(r["doc"]):
                    if s.startswith("materials/"):
                        mat_clean[s] += 1
                    stem_clean[title_stem(s)] += 1

    pdfs = sorted(fn for fn in os.listdir(MAT) if fn.lower().endswith(".pdf"))
    todo = []
    for fn in pdfs:
        eff = max(mat_clean.get("materials/" + fn, 0), stem_clean.get(title_stem("materials/" + fn), 0))
        if eff < KEEP_MIN:
            todo.append(fn)
    print(f"项目书 {len(pdfs)} 本 | 需补 {len(todo)} 本（追加模式，现有语料不动）", flush=True)

    done = set()
    if os.path.exists(DONE):
        done = {l.split("\t")[0].strip() for l in open(DONE, encoding="utf-8") if l.strip()}

    t0 = time.time()
    added_total = 0
    for i, fn in enumerate(todo):
        key = "materials/" + fn
        if key in done:
            continue
        path = os.path.join(MAT, fn)
        title = fn.rsplit(".", 1)[0][:55]
        print(f"[{i + 1}/{len(todo)}] OCR {title[:42]}", end=" ", flush=True)
        try:
            pages = []
            with pdfplumber.open(path) as pdf:
                tot = len(pdf.pages)
                for p in range(tot):
                    try:
                        x = ocr_page(pdf.pages[p])
                        if x:
                            pages.append(x)
                    except Exception:
                        pass
                    if (p + 1) % 100 == 0:
                        print(f"{p + 1}/{tot}", end=" ", flush=True)
            raw = chunks_of("\n\n".join(pages))
            # 整本 OCR 完后一次性写入，避免中途被杀产生半本重复
            recs = []
            for j, c in enumerate(raw):
                if is_good(c):
                    recs.append(json.dumps(
                        {"id": f"proj:{title}:{j}", "doc": c, "meta": {"title": title, "source": key}},
                        ensure_ascii=False))
            if recs:
                with open(MAIN, "a", encoding="utf-8") as out:
                    out.write("\n".join(recs) + "\n")
            added_total += len(recs)
            print(f"-> {len(pages)}页 {len(raw)}块 留{len(recs)} 丢{len(raw) - len(recs)}", flush=True)
            open(DONE, "a", encoding="utf-8").write(f"{key}\t{len(recs)}\n")
        except Exception as e:
            print(f"ERR {str(e)[:50]}", flush=True)
            open(DONE, "a", encoding="utf-8").write(f"{key}\tERR\n")

    rows = sum(1 for _ in open(MAIN, encoding="utf-8")) if os.path.exists(MAIN) else 0
    print(f"\n完成，用时 {(time.time() - t0) / 60:.0f} 分钟，新增 {added_total} 块", flush=True)
    print(f"语料现 {rows} 块。下一步：python reembed.py BAAI/bge-large-zh-v1.5  （续算，勿删 _emb.f32）→ python rebuild_stores.py", flush=True)


if __name__ == "__main__":
    main()
