import logging
import os
# LOG_LEVEL env → 控制 app.* logger 输出级别 (默认 WARNING, 验收/排障设 INFO)
# 注意: uvicorn 启动时会重设 logging, 这里我们强制覆盖 root logger 级别
_log_level = os.environ.get("LOG_LEVEL", "WARNING").upper()
logging.basicConfig(
    level=_log_level,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
    force=True,  # 强制覆盖 uvicorn 的 logging 配置
)
# 单独确保 uvicorn 的 logger 不会吞掉 app 日志
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.core.database import Base
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
from app.models.node_resource import NodeResource
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
from app.api.review import router as review_router
from app.api.recommend import router as recommend_router
from app.api.video import router as video_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="A3 个性化学习系统",
    description="基于大模型的个性化资源生成与学习多智能体系统",
    version="0.1.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """请求参数校验失败处理"""
    return JSONResponse(
        status_code=422,
        content={"detail": "请求参数无效", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """捕获所有未处理异常，防止 SSE 响应被异常关闭导致 ECONNRESET
    参考 Starlette/FastAPI 最佳实践：兜底异常处理器 + 详细日志
    """
    import uuid
    trace_id = uuid.uuid4().hex[:12]
    logger.error(
        "Unhandled exception trace_id=%s path=%s type=%s message=%s",
        trace_id, request.url.path, type(exc).__name__, str(exc),
        exc_info=True,
    )
    # 对 SSE 端点返回流式错误事件，避免 ECONNRESET
    if "/chat/send" in request.url.path or "/agent/" in request.url.path:
        from fastapi.responses import StreamingResponse
        import json as _json
        async def _error_stream():
            yield f"event: error\ndata: {_json.dumps({'message': '服务器内部错误', 'code': 'INTERNAL', 'trace_id': trace_id}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {_json.dumps({'status': 'error'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(
            _error_stream(),
            status_code=200,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Trace-Id": trace_id},
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误", "trace_id": trace_id},
        headers={"X-Trace-Id": trace_id},
    )

# ── 全局 404 处理器 — 返回 JSON 而不是 HTML，避免探针/监控噪声 ──
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "detail": "Endpoint not found",
                "path": request.url.path,
                "hint": "Try /api/health or /docs",
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
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
    """滑动窗口限流：已认证按user_id(500/min)，匿名按IP(60/min)。
    /api/health 和 / 根路径豁免（用于监控/探针）。"""
    if request.url.path in ("/api/health", "/"):
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
app.include_router(review_router)
app.include_router(recommend_router)
app.include_router(video_router)

# 静态文件挂载 (图片/音频/视频等生成资源)
_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(_static_dir, exist_ok=True)
os.makedirs(os.path.join(_static_dir, "images"), exist_ok=True)
os.makedirs(os.path.join(_static_dir, "audio"), exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

@app.on_event("startup")
async def init_db():
    import asyncio
    try:
        # 用 ensure_db_initialized() 拿到内部 _engine 引用,避免顶层 import engine 触发重连
        from app.core.database import ensure_db_initialized
        ensure_db_initialized()
        from app.core.database import _engine as _db_engine
        await asyncio.to_thread(Base.metadata.create_all, _db_engine)
        logger.info("数据库表初始化完成")
    except Exception as e:
        logger.warning("数据库连接失败: %s", e)
        logger.warning("服务已启动，但数据库功能不可用。请检查 MySQL 是否运行。")

    # JWT 安全校验: 启动时检测默认密钥
    if settings.jwt_secret_key == "change_this_to_random_string_32_chars":
        logger.warning("⚠️  JWT_SECRET_KEY 仍为默认值！请立即在 .env 中设置 JWT_SECRET_KEY")

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

    # 种子数据加载（开箱即用 - 首次启动时从仓库内 seed_data/ 自动入库）
    # 失败不阻断, 用户可手动 python scripts/load_seed_data.py --force 重试
    def _load_seed_data():
        try:
            # 用 importlib 避免路径问题
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "load_seed_data",
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "load_seed_data.py")
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                result = mod.load_seed_data(force=False)
                if not result.get("skipped") and (result.get("knowledge_base", 0) + result.get("exercise_bank", 0)) > 0:
                    logger.info(
                        "🌱 种子数据加载完成: knowledge_base=%d, exercise_bank=%d",
                        result.get("knowledge_base", 0), result.get("exercise_bank", 0)
                    )
        except Exception as e:
            logger.warning("种子数据加载失败 (非阻塞, 可手动重试): %s", e)
    threading.Thread(target=_load_seed_data, daemon=True).start()

    # 知识库教材索引（jieba + BM25，不依赖 BGE）
    def _load_content_library():
        try:
            from app.services.content_store import load_content_store
            count = load_content_store()
            logger.info("教材知识库索引完成 - %d 篇教材已加载", count)
        except Exception as e:
            logger.warning("教材知识库索引失败: %s", e)
    threading.Thread(target=_load_content_library, daemon=True).start()
    # Pre-warm DB engine (moves 10s delay to startup)
    try:
        from app.core.database import ensure_db_initialized
        ensure_db_initialized()
    except Exception:
        pass


@app.get("/")
async def root():
    """根路径欢迎页 — 防止监控/探针工具的 GET / 报 404"""
    return {
        "name": "A3 Learning System API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
async def health_check():
    status = {"status": "ok", "version": "0.1.0"}
    checks = {}

    # MySQL check
    try:
        from app.core.database import get_session
        from sqlalchemy import text
        with get_session() as db:
            db.execute(text("SELECT 1"))
        checks["mysql"] = "ok"
    except Exception as e:
        checks["mysql"] = f"error: {e}"
        status["status"] = "degraded"

    # Redis check
    try:
        import redis
        r = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
        r.close()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        status["status"] = "degraded"

    # ChromaDB check
    try:
        from app.core.chroma_client import get_collection
        col = get_collection("knowledge_base")
        checks["chromadb"] = f"ok ({col.count() if col else 0} docs)"
        # RAG model status
        try:
            from app.services.rag_service import is_rag_ready, is_bge_loading
            if is_rag_ready():
                checks["rag"] = "ready"
            elif is_bge_loading():
                checks["rag"] = "loading"
            else:
                checks["rag"] = "unavailable"
        except Exception:
            checks["rag"] = "error"
    except Exception as e:
        checks["chromadb"] = f"error: {e}"
        status["status"] = "degraded"

    status["checks"] = checks
    return status
