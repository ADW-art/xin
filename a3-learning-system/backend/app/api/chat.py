"""
对话 API —— SSE 流式端点

POST /api/chat/send → 接收用户消息 → 调用星火 → 逐字流式返回
"""

import json
import uuid
import logging
from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage

from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models.profile import LearningProfile
from app.models.user import User
from app.dependencies import get_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["对话"])#APIrouter


# ============================================================
# 请求模型：告诉 FastAPI 前端会传什么 JSON--校验字段，解析json
# ============================================================
class ChatRequest(BaseModel):
    content: str = Field(..., min_length=1, description="用户输入的消息")


# ============================================================
# 工具函数
# ============================================================
def _optional_user(authorization: str | None = Header(None), db=Depends(SessionLocal)):
    """可选认证：有 token 就解析用户，没有就返回 None"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = decode_access_token(authorization[7:])
    if not payload:
        return None
    return db.query(User).filter(User.id == int(payload["sub"])).first()


def _load_profile(user_id: int) -> dict | None:
    """从 MySQL 加载用户画像"""
    if not user_id:
        return None
    db = SessionLocal()
    try:
        row = db.query(LearningProfile).filter(LearningProfile.user_id == user_id).first()
        if not row:
            return None
        return {
            "knowledge_base": row.knowledge_base,
            "cognitive_style": row.cognitive_style,
            "learning_goal": row.learning_goal,
            "weekly_hours": row.weekly_hours,
            "error_patterns": row.error_patterns,
            "preferred_resource_type": row.preferred_resource_type,
            "dimension_scores": row.dimension_scores,
        }
    finally:
        db.close()


# ============================================================
# POST /api/chat/send —— 核心 SSE 端点
# ============================================================
@router.post("/send")
async def chat_send(
    request: ChatRequest,
    graph=Depends(get_graph),
    current_user: User | None = Depends(_optional_user),
):
    """发送消息 → LangGraph Supervisor 调度 → Agent 处理 → SSE 流式返回"""

    user_id = current_user.id if current_user else 0

    initial_state = {
        "messages": [HumanMessage(content=request.content)],
        "current_agent": "supervisor",
        "next_agent": None,
        "user_profile": _load_profile(user_id),
        "context": {},
        "agent_outputs": {},
        "stream_buffer": "",
        "user_id": user_id,
    }

    config = {"configurable": {"thread_id": str(uuid.uuid4())}} #thread_id 用于区分多轮对话
    #异步生成器--sse流式输出
    async def event_stream():
        prev_agent = "supervisor"
        try:
            #astream--langgraph异步流式执行方法
            #从入口开始执行，执行完一个节点就输出一下
            async for update in graph.astream(initial_state, config, stream_mode="updates"):
                #图有可能并行，一轮多个节点
                for node_name, node_update in update.items():
                    # 当前被调度的节点名--过滤掉不需要的节点
                    if node_name not in ("supervisor", "__end__"): #不是总调度/end时继续
                        agent_name = node_name

                        # Agent 切换通知-与之前不同时--提示
                        if agent_name != prev_agent:
                            yield f"event: agent_switch\ndata: {json.dumps({'from': prev_agent, 'to': agent_name}, ensure_ascii=False)}\n\n"
                            prev_agent = agent_name

                        # 流式缓冲区内容--有内容就往前推
                        buf = node_update.get("stream_buffer", "")
                        if buf:
                            yield f"event: message\ndata: {json.dumps({'content': buf, 'agent': agent_name}, ensure_ascii=False)}\n\n"

            yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse( #流式响应类-接收一个异步函数作为参数
        event_stream(),#返回内容
        media_type="text/event-stream",#MIME类型
        headers={
            "Cache-Control": "no-cache",#不让浏览器缓存
            "X-Accel-Buffering": "no",#不让nginx缓存-防止破坏流式效果
        },
    )
