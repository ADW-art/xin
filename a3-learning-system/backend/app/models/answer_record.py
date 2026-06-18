'''
答题记录模型

存储用户的答题记录，供评估 Agent 分析
'''
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.core.database import Base


class AnswerRecord(Base):
    __tablename__ = "answer_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    concept: Mapped[str | None] = mapped_column(String(128))  # 关联的知识点名称
    question_id: Mapped[int | None] = mapped_column(Integer)
    user_answer: Mapped[str | None] = mapped_column(String(1024))
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    time_spent: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user = relationship("User")
