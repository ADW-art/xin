'''
AgentState--通用数据格式,多agent连通模板
'''
from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class AgentState(TypedDict): #typeddict类型注解工具，定义字典里的每个字段的类型
    # 消息历史（LangGraph 自动追加新消息）
    messages: Annotated[list[BaseMessage], add_messages] #类型注解，添加额外元信息

    # 当前激活的 Agent 标识
    current_agent: str 

    # Supervisor 的路由决策结果
    next_agent: Optional[str] #可能有值

    # 用户的 6 维学习画像（从 MySQL 加载）
    user_profile: Optional[dict]

    # 当前对话上下文
    context: dict

    # 各 Agent 的输出缓存
    agent_outputs: dict

    # SSE 流式输出缓冲区——每个 Agent 往里写，外层逐段推给前端
    stream_buffer: str

    # 当前用户 ID（从 JWT 解析）
    user_id: int
