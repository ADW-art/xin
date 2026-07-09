"""
Auth API 端点测试 (FastAPI TestClient + Mock DB)

测试覆盖:
- POST /api/auth/register (成功 / 重复用户名 / 字段校验)
- POST /api/auth/login  (用户不存在 / 字段校验)
- GET  /api/auth/me     (无 token / 无效 token / 格式错误)

使用 MagicMock 替代真实 MySQL，无需外部依赖即可运行。
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import uuid

from app.main import app


@pytest.fixture
def client():
    """TestClient with mocked get_db dependency — no MySQL needed.

    Each test gets a fresh mock DB session with no pre-existing users.
    """
    from app.core.database import get_db

    mock_db = MagicMock()
    # Default: no existing user found in any query
    mock_db.query.return_value.filter.return_value.first.return_value = None

    app.dependency_overrides[get_db] = lambda: mock_db

    with TestClient(app) as c:
        # Attach mock so individual tests can customize behavior
        c._mock_db = mock_db
        yield c

    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════
# Registration endpoint tests
# ═══════════════════════════════════════════════════════════

def test_register_new_user(client):
    """新用户注册成功，返回 JWT token。"""
    unique = str(uuid.uuid4())[:8]
    resp = client.post("/api/auth/register", json={
        "username": f"test_{unique}",
        "password": "test123456",
    })
    assert resp.status_code in (200, 201), f"Unexpected {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_register_with_nickname(client):
    """带昵称的注册也应成功。"""
    unique = str(uuid.uuid4())[:8]
    resp = client.post("/api/auth/register", json={
        "username": f"test_{unique}",
        "password": "test123456",
        "nickname": "测试用户",
    })
    assert resp.status_code in (200, 201), f"Unexpected {resp.status_code}: {resp.text}"


def test_register_duplicate_username(client):
    """重复用户名注册返回 409 Conflict。"""
    # Configure mock: username already exists
    mock_user = MagicMock()
    mock_user.username = "existing_user"
    client._mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    resp = client.post("/api/auth/register", json={
        "username": "existing_user",
        "password": "test123456",
    })
    assert resp.status_code == 409
    assert "用户名已存在" in resp.json()["detail"]


def test_register_short_username(client):
    """用户名 < 3 字符 → 422 (Pydantic 校验)。"""
    resp = client.post("/api/auth/register", json={
        "username": "ab",
        "password": "test123456",
    })
    assert resp.status_code == 422


def test_register_short_password(client):
    """密码 < 6 字符 → 422 (Pydantic 校验)。"""
    resp = client.post("/api/auth/register", json={
        "username": "valid_user",
        "password": "12345",
    })
    assert resp.status_code == 422


def test_register_missing_username(client):
    """缺少必填字段 → 422。"""
    resp = client.post("/api/auth/register", json={
        "password": "test123456",
    })
    assert resp.status_code == 422


def test_register_missing_password(client):
    """缺少密码字段 → 422。"""
    resp = client.post("/api/auth/register", json={
        "username": "someone",
    })
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════
# Login endpoint tests
# ═══════════════════════════════════════════════════════════

def test_login_user_not_found(client):
    """不存在的用户登录 → 401。"""
    resp = client.post("/api/auth/login", json={
        "username": "nonexistent_user_99999",
        "password": "wrong_password",
    })
    assert resp.status_code == 401
    assert "错误" in resp.json()["detail"]


def test_login_wrong_password(client):
    """用户名存在但密码错误 → 401。

    模拟: 数据库中找到用户，但密码不匹配。
    """
    from app.core.security import hash_password

    mock_user = MagicMock()
    mock_user.username = "real_user"
    # 用真实哈希存储，这样 verify_password("wrong", hash) 返回 False
    mock_user.password_hash = hash_password("correct_password")
    client._mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    resp = client.post("/api/auth/login", json={
        "username": "real_user",
        "password": "wrong_password",
    })
    assert resp.status_code == 401
    assert "错误" in resp.json()["detail"]


def test_login_missing_password(client):
    """缺少密码字段 → 422。"""
    resp = client.post("/api/auth/login", json={
        "username": "someone",
    })
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════
# /me endpoint tests (authentication required)
# ═══════════════════════════════════════════════════════════

def test_me_without_token(client):
    """无 Authorization 头 → 401。"""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_with_invalid_token(client):
    """无效 JWT token → 401。"""
    resp = client.get("/api/auth/me", headers={
        "Authorization": "Bearer invalid.token.here",
    })
    assert resp.status_code == 401


def test_me_with_malformed_header(client):
    """Authorization 头不以 Bearer 开头 → 401。"""
    resp = client.get("/api/auth/me", headers={
        "Authorization": "NotBearer some_token",
    })
    assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════
# Logout endpoint tests
# ═══════════════════════════════════════════════════════════

def test_logout_without_token(client):
    """无 token 登出 → 401 (需要认证)。"""
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 401
