# 多智能体系统 — LangGraph
## 位置
a3-learning-system/backend/app/agents/
## 架构：Supervisor + 6 个 Agent
Supervisor（调度者）→ 意图分类 → 路由到对应 Agent
## Supervisor（supervisor.py）
- 用 LangGraph StateGraph 编排
- 接收用户消息 → 分类意图 → 路由到 Agent → 返回结果
- 支持多轮对话循环
- 状态用 SQLite checkpoint 持久化
## 意图分类（Prompt 驱动）
- chat: 闲聊/问候
- resource: 学习请求/知识查询/代码生成
- question: 出题/练习/答题/提交答案
- path: 学习路径/规划/下一步学什么
- evaluation: 评估/报告/进度检查
- profile: 描述学习背景/偏好
## Agent 列表
### chat_agent.py — 对话交互：直接调用 LLM 回复
### profile_agent.py — 用户画像：从对话中提取学习背景/目标/偏好
### resource_agent.py — 学习资源：生成学习内容+代码示例+RAG检索
### question_agent.py — 出题与批改：生成练习题+批改+答案检测
### path_agent.py — 学习路径：规划学习路线+推荐下一步
### evaluation_agent.py — 学习评估：6维评估+BKT算法+带Mermaid饼图
## 通信方式
- AgentState：所有 Agent 共享的状态字典
- current_agent：标记当前活跃 Agent
- agent_outputs：各 Agent 输出收集
- stream_buffer：流式输出内容
## 协作模式
- 支持多 Agent 并行协作（collaboration.py）
