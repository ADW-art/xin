import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 讯飞星火
    spark_app_id: str = ""
    spark_api_key: str = ""
    spark_api_secret: str = ""

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

    # BGE
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    embedding_device: str = "cpu"

    class Config:
        env_file = ".env"

settings = Settings()
