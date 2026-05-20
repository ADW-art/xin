from typing import Optional
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime

from app.core.database import Base
from app.models.profile import LearningProfile


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)#index给username建立索引
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[Optional[str]] = mapped_column(String(100), default=None)#
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), default=None)#
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    profile: Mapped[Optional["LearningProfile"]] = relationship("LearningProfile", back_populates="user", uselist=False)
    #关联模型(引号引用-防止执行到这里未定义)-怎么找-一对一/一对多?