"""
对话 API —— SSE 流式端点

POST /api/chat/send → 接收用户消息 → 调用星火 → 逐字流式返回
"""

import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.spark_client import SparkClient
from app.dependencies import get_spark_client

router = APIRouter(prefix="/api/chat", tags=["对话"])#APIrouter


# ============================================================
# 请求模型：告诉 FastAPI 前端会传什么 JSON
# ============================================================
class ChatRequest(BaseModel):
    content: str = Field(..., min_length=1, description="用户输入的消息")


# ============================================================
# POST /api/chat/send —— 核心 SSE 端点
# ============================================================
@router.post("/send")
async def chat_send(
    request: ChatRequest,
    spark: SparkClient = Depends(get_spark_client),#拿到依赖注入函数
):
    """发送消息，SSE 流式返回大模型生成的文本

    数据流：
      前端 POST JSON → 本端点 → spark_client.chat_stream()
        → WebSocket → 星火 API → 逐 token 返回
        → 本端点 yield SSE event → 前端 ReadableStream 逐字显示
    """

    # 把用户输入包装成星火要求的消息格式
    messages = [{"role": "user", "content": request.content}]

    # 生成器函数：逐 token → SSE 格式
    async def event_stream():
        try:
            for chunk in spark.chat_stream(messages):
                # 每个 chunk 是一小段文本（可能 1~5 个字）
                yield f"event: message\ndata: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

            # 全部完成，发结束信号
            yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

        except Exception as e:
            # 出错时通知前端
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
