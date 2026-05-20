"""
对话 API —— SSE 流式端点

POST /api/chat/send → 接收用户消息 → 调用星火 → 逐字流式返回
"""

import json
import uuid
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage

from app.dependencies import get_graph

router = APIRouter(prefix="/api/chat", tags=["对话"])#APIrouter


# ============================================================
# 请求模型：告诉 FastAPI 前端会传什么 JSON--校验字段，解析json
# ============================================================
class ChatRequest(BaseModel):
    content: str = Field(..., min_length=1, description="用户输入的消息")


# ============================================================
# POST /api/chat/send —— 核心 SSE 端点
# ============================================================
@router.post("/send")
async def chat_send(
    request: ChatRequest,
    graph=Depends(get_graph),
):
    """发送消息 → LangGraph Supervisor 调度 → Agent 处理 → SSE 流式返回"""

    initial_state = {
        "messages": [HumanMessage(content=request.content)],
        "current_agent": "supervisor",
        "next_agent": None,
        "user_profile": None,
        "context": {},
        "agent_outputs": {},
        "stream_buffer": "",
        "user_id": 0,  # 后续从 JWT 解析
    }

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async def event_stream():
        prev_agent = "supervisor"
        try:
            async for update in graph.astream(initial_state, config, stream_mode="updates"):
                for node_name, node_update in update.items():
                    # 当前被调度的节点名
                    if node_name not in ("supervisor", "__end__"):
                        agent_name = node_name

                        # Agent 切换通知
                        if agent_name != prev_agent:
                            yield f"event: agent_switch\ndata: {json.dumps({'from': prev_agent, 'to': agent_name}, ensure_ascii=False)}\n\n"
                            prev_agent = agent_name

                        # 流式缓冲区内容
                        buf = node_update.get("stream_buffer", "")
                        if buf:
                            yield f"event: message\ndata: {json.dumps({'content': buf, 'agent': agent_name}, ensure_ascii=False)}\n\n"

            yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),#返回内容
        media_type="text/event-stream",#MIME类型
        headers={
            "Cache-Control": "no-cache",#不让浏览器缓存
            "X-Accel-Buffering": "no",#不让nginx缓存
        },
    )
