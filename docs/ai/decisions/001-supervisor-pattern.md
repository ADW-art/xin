# 架构决策：使用 LangGraph Supervisor 模式

## 上下文
需要管理 6 个不同的 Agent，每个处理不同类型的用户请求

## 决策
使用 LangGraph StateGraph 的 Supervisor 模式：
一个中心 Supervisor Agent 负责意图分类和路由
6 个 Worker Agent 各自处理特定领域

## 优点
- 路由清晰，新增 Agent 只需要注册到 Supervisor 即可
- 状态管理统一，Agent 间通过共享 AgentState 通信

## 缺点
- Supervisor 的 Prompt 需要精确维护，否则意图分类会出错
- 多轮对话中 Agent 切换的上下文管理较复杂

## 备选方案
- 单个大 Prompt Agent（优点：简单；缺点：难以维护）
- 微服务独立 Agent（优点：独立部署；缺点：通信开销大）
