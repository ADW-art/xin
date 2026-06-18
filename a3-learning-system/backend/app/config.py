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

    # 讯飞星火
    spark_app_id: str = ""
    spark_api_key: str = ""
    spark_api_secret: str = ""
    spark_app_password: str = ""  # HTTP接口 Bearer Token (APPPassword)
    spark_model: str = "lite"  # lite / pro / max / 4.0Ultra（根据API Key权限选择）

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
    embedding_device: str = "cpu"
    # 本地模型路径（优先于在线下载，设为空则自动从 HF 下载/缓存加载）
    embedding_local_path: str = ""

    # LangGraph 持久化
    checkpoint_db_path: str = "./data/checkpoints.db"

settings = Settings()  # 创建全局对象
