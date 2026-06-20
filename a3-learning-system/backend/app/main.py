import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.database import engine, Base
from app.core.rate_limit import RateLimiter
from app.models.user import User
from app.models.profile import LearningProfile
from app.models.resource import Resource
from app.models.assessment import AssessmentReport
from app.models.learning_path import LearningPath
from app.models.conversation import Conversation
from app.models.answer_record import AnswerRecord
from app.models.bkt_state import BKTState
from app.models.review_schedule import ReviewScheduleModel
from app.api.chat import router as chat_router
from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.api.resources import router as resources_router
from app.api.assessment import router as assessment_router
from app.api.learning_path import router as learning_path_router
from app.api.conversation import router as conversation_router
from app.api.admin import router as admin_router
from app.api.bkt import router as bkt_router
from app.api.agent_trace import router as agent_trace_router
from app.api.tts import router as tts_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="A3 个性化学习系统",
    description="基于大模型的个性化资源生成与学习多智能体系统",
    version="0.1.0",
)

# ── CORS 中间件（从环境变量读取允许的来源） ──
cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 请求频率限制中间件 ──
_rate_limiter = RateLimiter(auth_limit=500, anon_limit=60, window_seconds=60)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """滑动窗口限流：已认证按user_id(500/min)，匿名按IP(60/min)。/api/health 豁免。"""
    if request.url.path == "/api/health":
        return await call_next(request)

    state = _rate_limiter.check(request)
    rate_limit_headers = {
        "X-RateLimit-Limit": str(state.limit),
        "X-RateLimit-Remaining": str(state.remaining),
        "X-RateLimit-Reset": str(state.reset_at),
    }

    if not state.allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁，请稍后再试"},
            headers=rate_limit_headers,
        )

    response = await call_next(request)
    response.headers.update(rate_limit_headers)
    return response

# 注册路由
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(resources_router)
app.include_router(assessment_router)
app.include_router(learning_path_router)
app.include_router(conversation_router)
app.include_router(admin_router)
app.include_router(bkt_router)
app.include_router(agent_trace_router)
app.include_router(tts_router)

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

    # BGE 模型后台预热（不阻塞启动，最多重试3次，未就绪时 Agent 自动降级为纯 LLM）
    import threading
    def _warmup():
        import time
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                from app.services.rag_service import _embed, is_rag_ready
                logger.info("BGE 模型预热中 (第 %d/%d 次)...", attempt, max_retries)
                _embed(["预热"])
                if is_rag_ready():
                    logger.info("BGE 模型预热完成 - RAG 就绪")
                    return
                else:
                    logger.warning("BGE 模型预热: 嵌入调用完成但模型未就绪 (第 %d/%d 次)", attempt, max_retries)
            except Exception as e:
                logger.warning("BGE 模型预热失败 (第 %d/%d 次): %s", attempt, max_retries, e)
            if attempt < max_retries:
                wait = 3 ** (attempt - 1)  # 1s, 3s, 9s
                logger.info("BGE 预热: %d秒后重试...", wait)
                time.sleep(wait)
        logger.warning("BGE 模型预热最终失败 - Agent 将使用纯 LLM 模式")
    threading.Thread(target=_warmup, daemon=True).start()

    # 习题库后台加载（BGE 预热后自动向量化入库）
    def _load_exercises():
        try:
            from app.services.rag_service import load_exercise_bank
            count = load_exercise_bank()
            if count > 0:
                logger.info("习题库加载完成 - %d 题已向量化入库", count)
            else:
                logger.info("习题库加载跳过 - 无新题或文件不存在")
        except Exception as e:
            logger.warning("习题库后台加载失败: %s", e)
    threading.Thread(target=_load_exercises, daemon=True).start()

    # 知识库教材索引（jieba + BM25，不依赖 BGE）
    def _load_content_library():
        try:
            from app.services.content_store import load_content_store
            count = load_content_store()
            logger.info("教材知识库索引完成 - %d 篇教材已加载", count)
        except Exception as e:
            logger.warning("教材知识库索引失败: %s", e)
    threading.Thread(target=_load_content_library, daemon=True).start()


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
