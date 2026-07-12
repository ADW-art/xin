# asyncio.wait_for 取消异步生成器导致 SSE 流式卡死

## 日期
2026-07-12

## 严重级别
P0 — 用户可见功能完全失效

## 症状
用户问第二个问题时前端"卡住不生成了"。具体表现: 首 token 延迟超过 8 秒时, SSE 流被杀死, 用户收到心跳消息后无任何实际内容输出。

## 根因
`chat.py` 流式循环使用 `asyncio.wait_for(_stream.__anext__(), timeout=8.0)` 做心跳检测。
`asyncio.wait_for` 超时后会取消内部 task, 将 `CancelledError` 注入异步生成器 `_bridge_stream`,
导致生成器关闭。后续 `__anext__()` 调用直接抛 `StopAsyncIteration`, 流式循环终止。

第二个问题携带更长对话历史 → 更大的 prompt → 首 token 延迟增加 → 更易触发 8s 超时。

## 修复
1. **chat.py**: 用 `asyncio.wait([chunk_task, hb_task])` 替代 `asyncio.wait_for`。
   心跳 task 完成时 chunk_task 保持运行, 不被取消。新增 120s 流式整体超时保护。
2. **state.py**: 新增 `_teaching_context_reducer`, `None` 表示清空而非合并为 `{}`。

## 涉及文件
- `backend/app/api/chat.py` (lines 701-740)
- `backend/app/agents/state.py` (lines 42-48, 87)

## 预防
- 禁止对异步生成器使用 `asyncio.wait_for` 做心跳
- 心跳必须用 `asyncio.wait` + 独立 sleep task, chunk task 永不被取消
- 所有流式循环必须有整体超时保护
