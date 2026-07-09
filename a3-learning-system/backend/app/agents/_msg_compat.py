"""LangGraph state messages 兼容性工具

背景: LangGraph 用 SQLite 做 checkpoint 持久化(state → JSON),下次恢复时
      LangChain 的 BaseMessage 对象会被还原成普通 dict,直接访问 .content 会
      抛 AttributeError: 'dict' object has no attribute 'content'

本模块提供兼容 BaseMessage / dict 两种格式的工具函数
"""
from __future__ import annotations


def _extract_content(msg) -> str:
    """从单条 message 中提取 content,兼容 BaseMessage / dict 两种格式"""
    if msg is None:
        return ""
    if isinstance(msg, dict):
        return msg.get("content", "") or ""
    # LangChain BaseMessage / 任何有 .content 属性的对象
    return getattr(msg, "content", "") or ""


def safe_get_content(msg) -> str | list:
    """通用: 安全获取单条消息的 content 字段

    与 _extract_content 区别: 不做 or "" 兜底,保留原始类型
    (用于 _build_llm_messages 这种需要 str 或 list[dict] 的场景)

    Args:
        msg: BaseMessage / dict / 任何带 .content 的对象

    Returns:
        content 字段原始值(str 或 list[dict] 多模态),失败返回 ""
    """
    if msg is None:
        return ""
    if isinstance(msg, dict):
        return msg.get("content", "")
    return getattr(msg, "content", "")


def last_msg_content(messages, default: str = "") -> str:
    """从 messages 列表取最后一条的 content

    Args:
        messages: 消息列表(BaseMessage 列表 / dict 列表 / 混合)
        default:  列表为空时返回的默认值

    Returns:
        最后一条消息的 content 字符串
    """
    if not messages:
        return default
    return _extract_content(messages[-1])


def all_msg_contents(messages) -> list[str]:
    """提取 messages 列表所有 content"""
    if not messages:
        return []
    return [_extract_content(m) for m in messages]
