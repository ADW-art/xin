"""
复习调度持久化模型

存储每个用户每个知识点的艾宾浩斯复习进度。
解决 ReviewScheduler 内存单例重启丢失的问题。
"""
from typing import Optional
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime

from app.core.database import Base


class ReviewScheduleModel(Base):
    __tablename__ = "review_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    concept: Mapped[str] = mapped_column(String(128), nullable=False)

    # 艾宾浩斯复习进度
    last_reviewed: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    interval_index: Mapped[int] = mapped_column(Integer, default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    memory_strength: Mapped[float] = mapped_column(Float, default=0.5)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # 联合唯一约束：同一用户的同一知识点只有一条记录
    __table_args__ = (
        UniqueConstraint("user_id", "concept", name="uq_user_concept"),
        {"comment": "艾宾浩斯复习调度状态表"},
    )
