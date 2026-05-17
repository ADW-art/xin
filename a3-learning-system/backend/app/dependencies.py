"""
FastAPI 依赖注入

所有 Depends(xxx) 函数集中在这里，方便复用和管理。
"""

from app.config import settings
from app.services.spark_client import SparkClient

# ============================================================
# SparkClient 全局单例
# ============================================================

_spark_client: SparkClient | None = None


def get_spark_client() -> SparkClient:
    """返回 SparkClient 的全局唯一实例（单例模式）

    为什么用单例：
      SparkClient 内部只存三个字符串（app_id/api_key/api_secret），
      没有可变状态。一个实例全局复用，避免每次请求都创建新对象。

    使用方式：
      @app.get("/chat")
      async def chat(spark: SparkClient = Depends(get_spark_client)):
          spark.chat_stream(...)
    """
    global _spark_client #赋值外部变量声明
    if _spark_client is None:
        _spark_client = SparkClient(
            app_id=settings.spark_app_id,
            api_key=settings.spark_api_key,
            api_secret=settings.spark_api_secret,
        )
    return _spark_client
