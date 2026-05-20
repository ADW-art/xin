'''
依赖注入(获取当前用户)+注册|登录|我的
'''
from fastapi import APIRouter, Depends, HTTPException, Header, status #拿请求头+状态码
from sqlalchemy.orm import Session #数据库会话

from app.core.database import get_db #获取数据库会话<--依赖注入
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token #加密+jwt方法
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse #格式
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["认证"])

#依赖注入-->获取当前用户
def get_current_user(authorization: str = Header(...), db: Session = Depends(get_db)) -> User:
    """从请求头提取 Bearer token → 解析 → 查数据库 → 返回 User 对象"""
    #请求头没Bearer,直接抛出错误
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证格式错误")
    #取后面的令牌+令牌失效抛错误
    payload = decode_access_token(authorization[7:])
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 无效或已过期")
    #db里面找用户
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user

#注册接口
@router.post("/register", response_model=TokenResponse)#返回格式是TokenResponse
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    #找
    existing = db.query(User).filter(User.username == body.username).first()
    #存在了
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    #创建用户->加密密码+存数据库
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        nickname=body.nickname,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id), "username": user.username})
    return TokenResponse(access_token=token) #直接返回令牌，不用再登录

#登录接口
@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.username == body.username).first()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    token = create_access_token({"sub": str(user.id), "username": user.username})
    return TokenResponse(access_token=token)#拿到令牌

#获取当前用户信息
@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user
