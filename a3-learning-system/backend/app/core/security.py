'''
项目安全模块--封装方法:密码加密+jwt令牌
'''
from datetime import datetime, timedelta#时间加减运算
from typing import Any#任何类型

from jose import jwt #创建+认证jwt令牌
from passlib.context import CryptContext #密码加密+认证
from app.config import settings #读取配置项

#bcrypt密码哈希加密算法
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") #方案列表-自动弃用算法+升级

#加密
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

#验证密码(同样方法加密后能否完全匹配)
def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

#创建jwt令牌
def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:#写入数据-过期时间
    to_encode = data.copy()#复制
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))#计算过期时间
    to_encode.update({"exp": expire}) #添加字段过期时间
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    #令牌+配置项读到的密钥+签名算法

#解析jwt令牌
def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except Exception:
        return None
