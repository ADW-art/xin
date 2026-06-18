"""
学习路径 ORM 模型

作用：
  定义 learning_paths 表的字段和关系
  存储 AI 生成的分阶段学习路径数据

关联文件：
  schemas/path.py         ← API 响应格式（基于本模型字段）
  api/learning_path.py    ← 使用本模型查询数据库
  core/database.py        ← 继承 Base，自动建表
"""
from sqlalchemy import String, Integer, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.core.database import Base


class LearningPath(Base):
    __tablename__ = "learning_paths"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    path_data: Mapped[dict | None] = mapped_column(JSON)
    current_node: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="active")
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user = relationship("User")
