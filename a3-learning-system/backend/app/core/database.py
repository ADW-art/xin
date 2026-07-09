"""Lazy SQLAlchemy engine initialization. Engine created on first use."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
from contextlib import contextmanager

DATABASE_URL = (
    f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
    f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    f"?charset=utf8mb4"
)

_engine = None
_session_maker = None

Base = declarative_base()


def ensure_db_initialized():
    """Lazy init database engine and session factory."""
    global _engine, _session_maker
    if _engine is not None:
        return
    _engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20,
                           pool_recycle=3600, pool_pre_ping=True, echo=False)
    _session_maker = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def SessionLocal():
    """Get a database session (lazy engine)."""
    ensure_db_initialized()
    return _session_maker()


def get_db():
    """FastAPI dependency: one DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()




@contextmanager
def get_session():
    """Context manager: for non-FastAPI DB sessions."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
