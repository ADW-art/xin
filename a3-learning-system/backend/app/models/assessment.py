"""
评估报告 ORM 模型

作用：
  定义 assessment_reports 表的字段和关系
  存储 AI 生成的学习评估报告数据

关联文件：
  schemas/assessment.py   ← API 响应格式（基于本模型字段）
  api/assessment.py       ← 使用本模型查询数据库
  core/database.py        ← 继承 Base，自动建表
"""
from sqlalchemy import String, Integer, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.core.database import Base


class AssessmentReport(Base):
    __tablename__ = "assessment_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(30), default="progress")
    report_data: Mapped[dict | None] = mapped_column(JSON)
    dimension_scores: Mapped[dict | None] = mapped_column(JSON)
    suggestions: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user = relationship("User")
