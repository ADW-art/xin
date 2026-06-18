"""
连接数据库

作用：
  创建 SQLAlchemy 引擎和会话工厂，提供数据库连接和 ORM 基类
  所有模型（Model）都继承本文件定义的 Base

关联文件：
  models/       ← 所有 ORM 模型继承 Base
  api/          ← 所有 API 通过 get_db() 获取数据库会话
  agents/       ← Agent 通过 SessionLocal() 直接创建会话
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

# 构建 MySQL 连接 URL
DATABASE_URL = (
    f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
    f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    f"?charset=utf8mb4"
)

# 创建数据库引擎（连接池：最少 10 个连接，最多 30 个）
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_recycle=3600, pool_pre_ping=True, echo=False)

# 会话工厂：每次 get_db() 或 SessionLocal() 创建一个新会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 基类：所有模型类继承这个 Base
Base = declarative_base()


def get_db():
    """FastAPI 依赖注入：每个请求创建一个数据库会话，请求结束自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


from contextlib import contextmanager


@contextmanager
def get_session():
    """上下文管理器：用于非 FastAPI 依赖注入场景的 DB 会话

    自动处理 commit/rollback/close，确保一致的会话生命周期管理。
    用法：
        with get_session() as db:
            row = db.query(...).first()
            # 读操作：commit 为 no-op
            # 写操作：自动 commit，异常时自动 rollback
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
