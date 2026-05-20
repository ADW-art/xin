'''
读画像数据，创建模型类
'''
from typing import Optional
from sqlalchemy import String, Integer, Float, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime

from app.core.database import Base


class LearningProfile(Base):
    __tablename__ = "learning_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    knowledge_base: Mapped[Optional[dict]] = mapped_column(JSON)
    cognitive_style: Mapped[Optional[str]] = mapped_column(String(20))
    learning_goal: Mapped[Optional[str]] = mapped_column(String(50))
    weekly_hours: Mapped[Optional[float]] = mapped_column(Float)
    error_patterns: Mapped[Optional[dict]] = mapped_column(JSON)
    preferred_resource_type: Mapped[Optional[str]] = mapped_column(String(20))
    dimension_scores: Mapped[Optional[dict]] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="profile")
