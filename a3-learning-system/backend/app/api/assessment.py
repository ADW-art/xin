"""
学习评估 API

作用：
  提供学习评估和答题记录的提交/查询接口
  用户可以提交答题结果、查看答题记录和评估报告

关联文件：
  models/assessment.py        ← AssessmentReport ORM 模型
  models/answer_record.py     ← AnswerRecord ORM 模型
  schemas/assessment.py       ← AssessmentResponse 响应格式
  main.py                     ← app.include_router(assessment_router)
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.schemas.assessment import AssessmentResponse
from app.models.assessment import AssessmentReport
from app.models.answer_record import AnswerRecord
from app.models.user import User
from app.api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assessment", tags=["评估"])


class AnswerSubmit(BaseModel):
    question_id: int
    user_answer: str
    is_correct: bool
    time_spent: int | None = None
    concept: str | None = None  # 关联的知识点（用于 BKT 追踪）


@router.post("/submit")
def submit_answer(body: AnswerSubmit, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = AnswerRecord(user_id=current_user.id, question_id=body.question_id, user_answer=body.user_answer, is_correct=body.is_correct, time_spent=body.time_spent)
    db.add(r)
    db.commit()

    # ── BKT 闭环: 答题结果 → 贝叶斯更新 P(known) ──
    if body.concept:
        try:
            from app.services.bkt_service import get_tracker
            from app.models.profile import LearningProfile

            tracker = get_tracker(current_user.id)
            node = tracker.get_or_create(body.concept)
            node.update(body.is_correct)
            tracker.persist_to_db()

            # 同步 knowledge_base (用真实 BKT 推算的 P(known))
            profile = db.query(LearningProfile).filter(
                LearningProfile.user_id == current_user.id
            ).first()
            if profile:
                kb = profile.knowledge_base or {}
                kb[body.concept] = round(node.p_known, 3)
                profile.knowledge_base = kb
                db.commit()

            logger.info("BKT闭环: '%s' correct=%s P(known)=%.3f",
                        body.concept, body.is_correct, node.p_known)
        except Exception as e:
            logger.warning("BKT闭环失败: %s", e)

    return {"id": r.id, "status": "ok"}


@router.get("/records")
def list_records(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(AnswerRecord)
        .filter(AnswerRecord.user_id == current_user.id)
        .order_by(AnswerRecord.created_at.desc())
        .all()
    )


@router.get("/reports", response_model=list[AssessmentResponse])
def list_reports(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(AssessmentReport)
        .filter(AssessmentReport.user_id == current_user.id)
        .order_by(AssessmentReport.created_at.desc())
        .all()
    )


@router.get("/reports/{report_id}", response_model=AssessmentResponse)
def get_report(report_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.query(AssessmentReport).filter(AssessmentReport.id == report_id, AssessmentReport.user_id == current_user.id).first()
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return r
