import os
from pathlib import Path

# HuggingFace 环境变量：默认允许在线下载
# 如需完全离线，在 .env 中设置 HF_HUB_OFFLINE=1 和 TRANSFORMERS_OFFLINE=1
os.environ.setdefault("HF_HUB_OFFLINE", "0")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "0")

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {
        "extra": "allow",
        "env_file": str(Path(__file__).resolve().parent.parent.parent / ".env"),
    }

    # 讯飞星火 (暂不使用，保留以备后续切回)
    spark_app_id: str = ""
    spark_api_key: str = ""
    spark_api_secret: str = ""
    spark_app_password: str = ""  # HTTP接口 Bearer Token (APPPassword)
    spark_model: str = "lite"  # lite / pro / max / 4.0Ultra

    # DeepSeek (当前使用)
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"  # deepseek-chat / deepseek-reasoner

    # 讯飞TTS (单独的应用凭据)
    tts_app_id: str = ""
    tts_api_key: str = ""
    tts_api_secret: str = ""

    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "a3_user"
    mysql_password: str = "a3_pass"
    mysql_database: str = "a3_learning"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # ChromaDB
    chroma_persist_dir: str = "./chroma_data"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"

    # JWT
    jwt_secret_key: str = "change_this_to_random_string_32_chars"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Rate Limit
    rate_limit_trust_proxy: bool = False  # 仅当运行在可信反代后方才开启 X-Forwarded-For

    # CORS
    cors_origins: str = "http://localhost:5173"

    # BGE
    hf_mirror: str = "https://hf-mirror.com"  # 设为空字符串 "" 使用官方 HuggingFace
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cuda"
    # 本地模型路径（优先于在线下载，设为空则自动从 HF 下载/缓存加载）
    embedding_local_path: str = "models/bge-large-zh-v1.5"
    # Reranker 模型名 + 本地路径（与 BGE-M3 一致：本地优先，缺失则 HF 下载）
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_local_path: str = ""  # 留空则从 HF 下载；推荐设为 models/BAAI_bge-reranker-v2-m3

    # LangGraph 持久化
    checkpoint_db_path: str = "./data/checkpoints.db"

settings = Settings()  # 创建全局对象


# ═══════════════════════════════════════════════════════════
# Agent 配置常量 — 照搬 Django settings.py 集中配置模式
# 禁止在业务代码中硬编码数值, 统一从此处引用
# ═══════════════════════════════════════════════════════════

# 画像追问: 每个会话最多触发追问次数
AGENT_MAX_ASK_PER_SESSION = 2

# 教学模式: 连续自动推进上限 (达到后暂停让用户消化)
AGENT_AUTO_ADVANCE_LIMIT = 3

# BKT 答题速度缓存 TTL (秒) — 5分钟
AGENT_SPEED_CACHE_TTL = 300

# 出题缓存 TTL (秒) — 24小时, 避免正常学习间隔导致上下文丢失
AGENT_QUESTION_CACHE_TTL = 86400

# SSE bridge 线程池: 最大 worker 数 (动态计算, 此值为回退下限)
AGENT_BRIDGE_MAX_WORKERS = 8

# LangGraph: 单次图执行递归上限
AGENT_RECURSION_LIMIT = 100

# 教学阶段边界间隔: 每 N 个节点触发一次阶段总结
AGENT_STAGE_BOUNDARY_INTERVAL = 3

# Checkpoint 修剪: 每个 thread 保留最近 N 个 checkpoint
AGENT_CHECKPOINT_KEEP_LAST = 20
