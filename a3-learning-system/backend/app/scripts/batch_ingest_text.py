"""
快跑脚本: 批量入库 top-20 文字版 PDF
直接运行，不依赖 argparse
"""
import io, sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.document_parser import parse_pdf
from app.services.rag_service import _embed, ingest_document, get_knowledge_count

PDF_BASE = "E:/code/github_clone/pdf-计算机专业资源/Some-Many-Books/PDF-file"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_CHUNKS = 200

# 全部 41 本文字版 PDF (按扫描结果排序，已入库的自动跳过)
BOOKS = [
    # 第一批 (20本，已入库)
    ("c", "C程序设计语言（第2版）.pdf"),
    ("javascript", "基于MVC的JavaScript_Web富应用开发.pdf"),
    ("others", "如何阅读一本书.pdf"),
    ("mongodb", "MongoDB实战.pdf"),
    ("linux", "跟我一起写makefile.pdf"),
    ("tcp", "TCP_IP详解卷1：协议.pdf"),
    ("tcp", "TCP_IP详解卷2：实现.pdf"),
    ("golang", "Go学习笔记（第6版下卷）.pdf"),
    ("clean-code", "程序设计实践.pdf"),
    ("python", "Python_Cookbook.pdf"),
    ("python", "python核心编程.pdf"),
    ("git", "ProGit中文版.pdf"),
    ("javascript", "javascript面向对象编程.pdf"),
    ("clean-code", "程序设计方法.pdf"),
    ("tcp", "TCP_IP详解卷3：TCP事务协议，HTTP，NNTP和UNIX域协议.pdf"),
    ("clean-code", "修改代码的艺术.pdf"),
    ("clean-code", "代码大全.pdf"),
    ("golang", "go程序设计语言.pdf"),
    ("mysql", "MySQL必知必会.pdf"),
    ("golang", "Go语言实战.pdf"),
    # 第二批 (21本，待入库)
    ("docker", "Docker从入门到实践（第3版）.pdf"),
    ("clean-code", "重构：改善既有代码的设计.pdf"),
    ("system", "高性能网站建设指南.pdf"),
    ("nginx", "深入理解Nginx：模块开发与架构解析（第2版）.pdf"),
    ("others", "七周七语言：理解多种编程范型.pdf"),
    ("golang", "Go源码剖析.pdf"),
    ("mongodb", "深入学习MongoDB.pdf"),
    ("redis", "Redis开发与运维.pdf"),
    ("nodejs", "Node.js开发指南.pdf"),
    ("golang", "Go学习笔记（第4版）.pdf"),
    ("http", "HTTP权威指南.pdf"),
    ("python", "Python编程：从入门到实践.pdf"),
    ("nodejs", "深入浅出Node.js.pdf"),
    ("git", "GitHub入门与实践.pdf"),
    ("nodejs", "Node.js实战.pdf"),
    ("javascript", "你不知道的JavaScript（中卷）.pdf"),
    ("javascript", "你不知道的JavaScript（下卷）.pdf"),
    ("http", "Web性能权威指南.pdf"),
    ("computer-system", "计算的本质：深入剖析程序和计算机.pdf"),
    ("nodejs", "Node与Express开发.pdf"),
    ("others", "程序员的职业素养.pdf"),
]

def chunk_text(text):
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        c = text[start:end].strip()
        if c: chunks.append(c)
        start += CHUNK_SIZE - CHUNK_OVERLAP
        if len(chunks) >= MAX_CHUNKS: break
    return chunks

done_file = os.path.join(os.path.dirname(__file__), '..', '..', 'pdf_ingest_done.txt')
already_done = set()
if os.path.exists(done_file):
    with open(done_file, 'r', encoding='utf-8') as f:
        already_done = set(line.strip() for line in f)

total_start = time.time()
for idx, (subject, filename) in enumerate(BOOKS):
    key = f"{subject}/{filename}"
    if key in already_done:
        print(f"[{idx+1}/{len(BOOKS)}] SKIP {key}")
        continue

    path = os.path.join(PDF_BASE, subject, filename)
    if not os.path.exists(path):
        print(f"[{idx+1}/{len(BOOKS)}] MISS {key}")
        continue

    t0 = time.time()
    print(f"\n[{idx+1}/{len(BOOKS)}] {key}", flush=True)

    try:
        paras = parse_pdf(path, use_ocr=False)
    except Exception as e:
        print(f"  PARSE ERROR: {e}")
        with open(done_file, 'a', encoding='utf-8') as f: f.write(key + '\n')
        continue

    cleaned = [p['content'].strip() for p in paras if len(p['content'].strip()) > 20]
    if not cleaned:
        print(f"  EMPTY after clean")
        with open(done_file, 'a', encoding='utf-8') as f: f.write(key + '\n')
        continue

    full = '\n\n'.join(cleaned)
    chunks = chunk_text(full)
    title = filename.rsplit('.', 1)[0]

    ok = 0
    for i, c in enumerate(chunks):
        try:
            emb = _embed([c])[0]
            ingest_document(content=c, title=title, source=key, doc_id=f"{subject}:{title}:chunk{i}")
            ok += 1
        except Exception as e:
            print(f"  CHUNK{i} ERR: {e}")

    elapsed = time.time() - t0
    print(f"  DONE: {ok}/{len(chunks)} chunks, {len(full)} chars, {elapsed:.0f}s", flush=True)

    with open(done_file, 'a', encoding='utf-8') as f:
        f.write(key + '\n')

print(f"\n{'='*50}")
print(f"Total: {time.time()-total_start:.0f}s, KB now: {get_knowledge_count()}")
