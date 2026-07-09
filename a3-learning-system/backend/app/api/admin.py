"""
教材管理 API

提供教材上传、知识库管理、版本控制功能
"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.api.auth import get_current_user
from app.services.document_parser import parse_uploaded_pdf, parse_markdown, parse_docx, parse_file
from app.services.rag_service import ingest_document, get_knowledge_count

router = APIRouter(prefix="/api/admin", tags=["管理"])

KB_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts", "knowledge_materials")
os.makedirs(KB_DIR, exist_ok=True)


@router.get("/rag-trace")
def rag_trace_endpoint(
    query: str = Query(..., min_length=1, description="检索查询文本"),
    current_user: User = Depends(get_current_user),
):
    """RAG 检索流水线可视化追踪

    返回完整四阶段中间结果：Dense召回 → BM25召回 → RRF融合 → CrossEncoder精排
    用于前端 RagCenter 页面展示检索过程。
    """
    from app.services.rag_service import rag_trace
    return rag_trace(query)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """上传教材 PDF/Word/Markdown → 解析 → 入库"""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".doc", ".md", ".txt"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的文件格式: {suffix}")

    content = await file.read()
    temp_path = os.path.join(KB_DIR, f"_upload_{uuid.uuid4().hex[:8]}{suffix}")
    with open(temp_path, "wb") as f:
        f.write(content)

    try:
        paragraphs = parse_file(temp_path)
    except Exception as e:
        os.remove(temp_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"解析失败: {e}")

    # 按章节/段落聚合后入库
    full_text = "\n\n".join(p["content"] for p in paragraphs)
    title = file.filename.replace(suffix, "")
    # 尝试从内容中提取标题
    for line in full_text.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            break

    doc_id = ingest_document(title=title, content=full_text, source=f"用户上传: {file.filename}")

    # 清除 KG 词汇表缓存（新教材可能包含新概念）
    try:
        from app.services.bkt_service import invalidate_kg_vocabulary
        invalidate_kg_vocabulary()
    except Exception:
        pass

    os.remove(temp_path)

    return {
        "id": doc_id,
        "title": title,
        "paragraphs": len(paragraphs),
        "size": len(content),
        "knowledge_base_total": get_knowledge_count(),
    }


@router.get("/stats")
def get_stats(current_user: User = Depends(get_current_user)):
    """知识库统计信息"""
    from app.core.chroma_client import get_collection
    stats = {"knowledge_base": get_knowledge_count()}
    try:
        ex_col = get_collection("exercise_bank")
        r = ex_col.get()
        stats["exercise_bank"] = len(r["ids"]) if r and r.get("ids") else 0
    except Exception:
        stats["exercise_bank"] = 0
    return stats


@router.get("/rag-status")
def rag_status():
    """返回 RAG 系统就绪状态（前端轮询用，无需登录）"""
    from app.services.rag_service import is_rag_ready, is_bge_loading
    from app.services.content_store import is_content_ready as cs_ready
    return {
        "rag_ready": is_rag_ready(),
        "content_store_ready": cs_ready(),
        "loading": is_bge_loading(),
    }


@router.post("/rag-load")
async def rag_load():
    """主动触发 BGE-M3 加载（诊断用，主人排查 BGE 是否成功）"""
    from app.services.rag_service import get_dense_model
    import time as _time
    t0 = _time.time()
    try:
        model = get_dense_model()
        elapsed = _time.time() - t0
        from app.services.rag_service import is_rag_ready
        return {
            "ok": True,
            "loaded": model is not None,
            "ready": is_rag_ready(),
            "elapsed_sec": round(elapsed, 2),
        }
    except Exception as e:
        elapsed = _time.time() - t0
        return {
            "ok": False,
            "loaded": False,
            "ready": False,
            "elapsed_sec": round(elapsed, 2),
            "error": str(e),
        }
