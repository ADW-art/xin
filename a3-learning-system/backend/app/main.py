import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import engine, Base
from app.models.user import User
from app.models.profile import LearningProfile
from app.api.chat import router as chat_router
from app.api.auth import router as auth_router
from app.api.profile import router as profile_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="A3 个性化学习系统",
    description="基于大模型的个性化资源生成与学习多智能体系统",
    version="0.1.0",
)

#中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(profile_router)

@app.on_event("startup")
async def init_db():
    import asyncio
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, Base.metadata.create_all, engine
        )
        logger.info("数据库表初始化完成")
    except Exception as e:
        logger.warning("数据库连接失败: %s", e)
        logger.warning("服务已启动，但数据库功能不可用。请检查 MySQL 是否运行。")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
