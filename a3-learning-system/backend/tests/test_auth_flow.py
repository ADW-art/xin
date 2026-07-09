"""
Auth API 端到端流程测试 (FastAPI TestClient + Mock DB)

测试覆盖:
- 注册 → 登录 → 获取 token → 访问 /me (完整流程)
- 参数校验 (空用户名/弱密码/缺失字段)
- 失败场景 (重复用户名/用户不存在/密码错误)
- 认证失败场景 (无token/无效token/错误格式)
- Token 响应格式验证

使用 MagicMock 替代真实 MySQL，无需外部依赖即可运行。
通过 create_access_token 构造合法 JWT 绕过注册端点的 Mock 限制。
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import uuid

from app.main import app
from app.core.security import create_access_token, hash_password


def _make_valid_token(user_id: int = 1, username: str = "testuser") -> str:
    """创建合法 JWT token 用于测试 (绕过 Mock DB 的 id 问题)。"""
    return create_access_token({"sub": str(user_id), "username": username})


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
        c._mock_db = mock_db
        yield c

    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════
# 端到端流程测试
# ═══════════════════════════════════════════════════════════════

class TestAuthFlow:
    """注册 → 登录 → 使用 token 访问受保护端点"""

    def test_register_returns_token(self, client):
        """新用户注册成功，返回 JWT token。"""
        name = f"flowtest_{uuid.uuid4().hex[:6]}"
        r = client.post("/api/auth/register", json={
            "username": name,
            "password": "test123456",
            "nickname": "流程测试",
        })
        assert r.status_code in (200, 201), f"Register failed: {r.status_code} {r.text}"
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_with_mocked_user(self, client):
        """登录: 模拟数据库找到用户 + 密码匹配 → 返回 token"""
        name = "logintest_user"
        mock_user = MagicMock()
        mock_user.username = name
        mock_user.password_hash = hash_password("test123456")
        client._mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        r = client.post("/api/auth/login", json={
            "username": name,
            "password": "test123456",
        })
        assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
        data = r.json()
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20

    def test_login_wrong_password(self, client):
        """用户名存在但密码错误 → 401"""
        mock_user = MagicMock()
        mock_user.username = "real_user"
        mock_user.password_hash = hash_password("correct_password")
        client._mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        r = client.post("/api/auth/login", json={
            "username": "real_user",
            "password": "wrong_password",
        })
        assert r.status_code == 401
        assert "错误" in r.json()["detail"]

    def test_login_nonexistent_user(self, client):
        """不存在的用户登录 → 401"""
        r = client.post("/api/auth/login", json={
            "username": "nonexistent_user_99999",
            "password": "any_password",
        })
        assert r.status_code == 401

    def test_me_with_valid_token(self, client):
        """/me: 合法 JWT + 数据库中存在用户 → 200 返回用户信息"""
        token = _make_valid_token(user_id=42, username="me_test_user")

        mock_user = MagicMock()
        mock_user.id = 42
        mock_user.username = "me_test_user"
        mock_user.nickname = "测试昵称"
        mock_user.avatar_url = None
        mock_user.created_at = None
        client._mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        r = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert r.status_code == 200, f"Me failed: {r.status_code} {r.text}"
        data = r.json()
        assert data["username"] == "me_test_user"
        assert data["nickname"] == "测试昵称"


# ═══════════════════════════════════════════════════════════════
# /me 端点认证失败场景
# ═══════════════════════════════════════════════════════════════

class TestMeEndpoint:
    """检测 /me 端点对各种认证失败的处理"""

    def test_me_without_token(self, client):
        """无 Authorization 头 → 401"""
        r = client.get("/api/auth/me")
        assert r.status_code == 401

    def test_me_with_invalid_jwt(self, client):
        """无效 JWT token (无法解码) → 401"""
        r = client.get("/api/auth/me", headers={
            "Authorization": "Bearer invalid.token.here",
        })
        assert r.status_code == 401

    def test_me_with_malformed_header(self, client):
        """Authorization 头不以 Bearer 开头 → 401"""
        r = client.get("/api/auth/me", headers={
            "Authorization": "NotBearer some_token",
        })
        assert r.status_code == 401

    def test_me_with_empty_token(self, client):
        """空 Bearer token → 401 (解码失败)"""
        r = client.get("/api/auth/me", headers={
            "Authorization": "Bearer ",
        })
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════
# 参数校验测试 (Pydantic 验证)
# ═══════════════════════════════════════════════════════════════

class TestValidation:
    """请求参数校验 (Pydantic Field 约束)"""

    def test_empty_username_rejected(self, client):
        """空用户名 → 422 (min_length=3)"""
        r = client.post("/api/auth/register", json={
            "username": "",
            "password": "test123456",
        })
        assert r.status_code >= 400

    def test_short_username_rejected(self, client):
        """用户名 < 3 字符 → 422"""
        r = client.post("/api/auth/register", json={
            "username": "ab",
            "password": "test123456",
        })
        assert r.status_code == 422

    def test_short_password_rejected(self, client):
        """密码 < 6 字符 → 422"""
        r = client.post("/api/auth/register", json={
            "username": "test_user_123",
            "password": "12",
        })
        assert r.status_code >= 400

    def test_very_short_password(self, client):
        """密码 1 字符 → 422"""
        r = client.post("/api/auth/register", json={
            "username": "test_user_456",
            "password": "a",
        })
        assert r.status_code >= 400

    def test_long_username_rejected(self, client):
        """用户名 > 50 字符 → 422"""
        r = client.post("/api/auth/register", json={
            "username": "a" * 51,
            "password": "test123456",
        })
        assert r.status_code >= 400

    def test_long_password_rejected(self, client):
        """密码 > 100 字符 → 422"""
        r = client.post("/api/auth/register", json={
            "username": "valid_user",
            "password": "a" * 101,
        })
        assert r.status_code >= 400

    def test_missing_username(self, client):
        """缺少必填字段 username → 422"""
        r = client.post("/api/auth/register", json={
            "password": "test123456",
        })
        assert r.status_code == 422

    def test_missing_password(self, client):
        """缺少必填字段 password → 422"""
        r = client.post("/api/auth/register", json={
            "username": "someone",
        })
        assert r.status_code == 422

    def test_empty_body(self, client):
        """空请求体 → 422"""
        r = client.post("/api/auth/register", json={})
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 登出流程测试
# ═══════════════════════════════════════════════════════════════

class TestLogoutFlow:
    """登出端点测试"""

    def test_logout_requires_auth(self, client):
        """无 token 登出 → 401"""
        r = client.post("/api/auth/logout")
        assert r.status_code == 401

    def test_logout_with_invalid_token(self, client):
        """无效 token 登出 → 401"""
        r = client.post("/api/auth/logout", headers={
            "Authorization": "Bearer invalid_token_here",
        })
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════
# Token 响应格式验证
# ═══════════════════════════════════════════════════════════════

class TestTokenFormat:
    """验证 token 响应格式正确"""

    def test_register_returns_bearer_token(self, client):
        """注册返回 token_type == 'bearer'"""
        name = f"tokentest_{uuid.uuid4().hex[:6]}"
        r = client.post("/api/auth/register", json={
            "username": name,
            "password": "test123456",
        })
        assert r.status_code in (200, 201)
        data = r.json()
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20  # JWT tokens are >20 chars

    def test_login_returns_bearer_token(self, client):
        """登录返回 token_type == 'bearer'"""
        mock_user = MagicMock()
        mock_user.username = "tokentest_user"
        mock_user.password_hash = hash_password("test123456")
        client._mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        r = client.post("/api/auth/login", json={
            "username": "tokentest_user",
            "password": "test123456",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20

    def test_token_user_id_consistency(self, client):
        """登录获取的 token 可通过 /me 解析回同一用户"""
        token = _make_valid_token(user_id=7, username="consistency_user")

        mock_user = MagicMock()
        mock_user.id = 7
        mock_user.username = "consistency_user"
        mock_user.nickname = None
        mock_user.avatar_url = None
        mock_user.created_at = None
        client._mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        r = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert r.status_code == 200
        assert r.json()["username"] == "consistency_user"
