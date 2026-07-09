import os, sys, types
os.environ.setdefault("TESTING", "1")

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from unittest.mock import MagicMock, patch

# 模块级 mock
_cm = types.ModuleType("chromadb")
_cm.config = types.ModuleType("chromadb.config")
_cm.config.Settings = MagicMock()
sys.modules["chromadb"] = _cm
sys.modules["chromadb.config"] = _cm.config

_st = types.ModuleType("sentence_transformers")
_st.SentenceTransformer = MagicMock()
sys.modules["sentence_transformers"] = _st

_hf = types.ModuleType("huggingface_hub")
_hf.constants = types.ModuleType("huggingface_hub.constants")
_hf.configure_http_backend = MagicMock()   # 缺了这个导致 ImportError
sys.modules["huggingface_hub"] = _hf
sys.modules["huggingface_hub.constants"] = _hf.constants

sys.modules["redis"] = MagicMock()
sys.modules["torch"] = MagicMock()

_patcher_create = patch("sqlalchemy.create_engine", return_value=MagicMock())
_patcher_create.start()

from app.core.database import SessionLocal, Base, SessionLocal
_engine_mock = MagicMock()
_patcher_engine = patch("app.core.database._engine", _engine_mock, create=True)
_patcher_engine.start()
_patcher_session = patch("app.core.database.SessionLocal", SessionLocal)
_patcher_session.start()
_patcher_ratelimit = patch("app.core.rate_limit.RateLimiter", MagicMock())
_patcher_ratelimit.start()

import pytest

def pytest_unconfigure():
    _patcher_create.stop()
    _patcher_engine.stop()
    _patcher_session.stop()
    _patcher_ratelimit.stop()
