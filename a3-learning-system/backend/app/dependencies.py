"""
FastAPI 依赖注入

所有 Depends(xxx) 函数集中在这里，方便复用和管理。
"""

from app.config import settings
from app.services.deepseek_client import DeepSeekClient

# ============================================================
# LLM 客户端全局单例 (当前: DeepSeek，Spark 代码保留备用)
# ============================================================

_llm_client: DeepSeekClient | None = None

def get_spark_client() -> DeepSeekClient:
    """返回 LLM 客户端的全局唯一实例（单例模式）

    当前使用 DeepSeek，接口兼容原 SparkClient。
    切换回 Spark: 修改此函数创建 SparkClient 即可。

    使用方式：
      @app.get("/chat")
      async def chat(spark = Depends(get_spark_client)):
          spark.chat_stream(...)
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = DeepSeekClient(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
        )
    return _llm_client


# ============================================================
# LangGraph 图实例（单例，基于同一个 SparkClient）
# ============================================================

_graph = None


def get_graph():
    """返回编译好的 LangGraph 图（单例）"""
    global _graph
    if _graph is None:
        from app.agents.supervisor import build_graph
        _graph = build_graph(get_spark_client())
    return _graph
