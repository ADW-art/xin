"""
对话历史 API

作用：
  提供对话历史的查询接口
  用户可以查看历史对话列表和某次对话的详细内容

关联文件：
  models/conversation.py         ← Conversation ORM 模型
  main.py                        ← app.include_router(conversation_router)
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.models.conversation import Conversation
from app.models.user import User
from app.api.auth import get_current_user

router = APIRouter(prefix="/api/chat", tags=["对话"])


class HistoryItem(BaseModel):
    id: int
    role: str
    content: str
    agent_type: str | None = None
    created_at: str


@router.get("/history", response_model=list[HistoryItem])
def get_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.asc())
        .limit(limit)
        .all()
    )
    return [
        HistoryItem(
            id=row.id,
            role=row.role,
            content=row.content,
            agent_type=row.agent_type,
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]


class DeleteHistoryResponse(BaseModel):
    deleted: int


@router.delete("/history/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除指定的对话记录（仅限当前用户）"""
    row = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话记录不存在")
    db.delete(row)
    db.commit()
    return {"deleted": 1, "id": conversation_id}


@router.delete("/history", response_model=DeleteHistoryResponse)
def delete_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除当前用户的所有对话历史"""
    count = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .delete()
    )
    db.commit()
    return DeleteHistoryResponse(deleted=count)
