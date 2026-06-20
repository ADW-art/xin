from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db #获取数据库会话
from app.schemas.profile import ProfileUpdate, ProfileResponse #数据库契约格式
from app.models.profile import LearningProfile #orm模型
from app.models.user import User 
from app.api.auth import get_current_user #获取当前登录用户

router = APIRouter(prefix="/api/profile", tags=["画像"])

#orm模型转api响应格式
def _profile_to_response(p: LearningProfile) -> ProfileResponse:
    return ProfileResponse(
        user_id=p.user_id,
        knowledge_base=p.knowledge_base,
        cognitive_style=p.cognitive_style,
        learning_goal=p.learning_goal,
        weekly_hours=p.weekly_hours,
        error_patterns=p.error_patterns,
        preferred_resource_type=p.preferred_resource_type,
        dimension_scores=p.dimension_scores,
        suggestions=p.suggestions,
    )

# JSON fields that need deep merge instead of full replacement
_JSON_MERGE_FIELDS = {'knowledge_base', 'error_patterns', 'dimension_scores'}

#更新orm
def _update_fields(p: LearningProfile, data: ProfileUpdate):
    for field, value in data.model_dump(exclude_unset=True).items(): #将模型转化为字典-只更新传了的字段
        if field in _JSON_MERGE_FIELDS and value is not None:
            existing = getattr(p, field, None) or {}
            if isinstance(existing, dict) and isinstance(value, dict):
                # deep merge: new keys override, omitted keys preserved
                merged = dict(existing)
                merged.update(value)
                setattr(p, field, merged)
                continue
            if isinstance(existing, list) and isinstance(value, list):
                # for error_patterns list, replace entirely when explicitly provided
                setattr(p, field, value)
                continue
        setattr(p, field, value) #设置动态对象属性  p.field=value

#获取画像
@router.get("/me", response_model=ProfileResponse)
def get_my_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.query(LearningProfile).filter(LearningProfile.user_id == current_user.id).first() #查数据库，找画像
    if not profile:
        # 首次访问，创建空画像
        try:
            profile = LearningProfile(user_id=current_user.id)
            db.add(profile) #添加
            db.commit() #写入数据库
            db.refresh(profile) #刷新
        except Exception:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="创建画像失败")
    return _profile_to_response(profile) #转换格式后返回

#更新画像
@router.put("/me", response_model=ProfileResponse)
def update_my_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(LearningProfile).filter(LearningProfile.user_id == current_user.id).first()
    if not profile:
        profile = LearningProfile(user_id=current_user.id)
        db.add(profile)
    _update_fields(profile, body)
    try:
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新画像失败")
    return _profile_to_response(profile)
