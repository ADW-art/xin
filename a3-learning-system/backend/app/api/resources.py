"""
学习资源 API

作用：
  提供已生成学习资源的查询接口
  用户可以按类型筛选资源列表、查看资源详情

关联文件：
  models/resource.py          ← Resource ORM 模型
  schemas/resource.py         ← ResourceListResponse / ResourceDetailResponse 响应格式
  main.py                     ← app.include_router(resources_router)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.resource import ResourceListResponse, ResourceDetailResponse, FeedbackRequest, FeedbackResponse, DeleteResponse
from app.models.resource import Resource
from app.models.user import User
from app.api.auth import get_current_user

router = APIRouter(prefix="/api/resources", tags=["资源"])


@router.get("", response_model=list[ResourceListResponse])
def list_resources(
    resource_type: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Resource).filter(Resource.user_id == current_user.id)
    if resource_type:
        q = q.filter(Resource.resource_type == resource_type)
    if keyword:
        kw = f"%{keyword}%"
        q = q.filter(Resource.title.like(kw) | Resource.content.like(kw))
    return q.order_by(Resource.created_at.desc()).offset((page - 1) * size).limit(size).all()


@router.get("/{resource_id}", response_model=ResourceDetailResponse)
def get_resource(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.query(Resource).filter(Resource.id == resource_id, Resource.user_id == current_user.id).first()
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")
    return r


@router.post("/{resource_id}/feedback", response_model=FeedbackResponse)
def set_resource_feedback(
    resource_id: int,
    body: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """为学习资源评分（1-5分）"""
    r = db.query(Resource).filter(Resource.id == resource_id, Resource.user_id == current_user.id).first()
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")
    r.feedback_score = body.score
    db.commit()
    db.refresh(r)
    return FeedbackResponse(
        id=r.id,
        feedback_score=r.feedback_score,
        message="评分已提交",
    )


@router.delete("/{resource_id}", response_model=DeleteResponse)
def delete_resource(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除学习资源（仅限资源所属用户）

    P1-16: 同时删除关联的 NodeResource 记录，防止孤儿引用。
    """
    r = db.query(Resource).filter(Resource.id == resource_id, Resource.user_id == current_user.id).first()
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")
    # 级联清理关联表中的记录
    from app.models.node_resource import NodeResource
    db.query(NodeResource).filter(NodeResource.resource_id == resource_id).delete()
    db.delete(r)
    db.commit()
    return DeleteResponse(deleted=True)
