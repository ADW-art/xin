"""
学习资源 ORM 模型

作用：
  定义 resources 表的字段和关系
  存储 AI 生成的学习资源（文档/代码/题目等）

关联文件：
  schemas/resource.py     ← API 响应格式（基于本模型字段）
  api/resources.py        ← 使用本模型查询数据库
  core/database.py        ← 继承 Base，自动建表
"""
from sqlalchemy import String, Integer, Text, JSON, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.core.database import Base


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    knowledge_points: Mapped[dict | None] = mapped_column(JSON)
    difficulty_level: Mapped[int | None] = mapped_column(Integer)
    generated_by: Mapped[str | None] = mapped_column(String(30))
    feedback_score: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user = relationship("User")
