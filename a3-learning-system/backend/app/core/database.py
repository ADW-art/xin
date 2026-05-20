'''
连接数据库
'''
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

DATABASE_URL = (
    f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
    f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    f"?charset=utf8mb4"
)

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_recycle=3600, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)#会话工厂

Base = declarative_base()#继承orm模型的基类

def get_db():#连接数据库，拿到会话-->用于依赖注入
    """FastAPI 依赖注入：每个请求创建一个数据库会话，请求结束自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
