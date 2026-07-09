# A3 学习系统 - AI 知识库索引

## 治理体系文件
- 主规则: CLAUDE.md
- Agent 定义: .claude/agents/*.md
- 通信协议: .claude/schemas/*.yaml
- 架构规则: .claude/rules/architecture.md
- 闸门规则: .claude/rules/gates.md
- 项目地图: .claude/rules/project-map.md

## 后端核心架构
- FastAPI 入口: backend/app/main.py
- LangGraph 多智能体编排: backend/app/agents/supervisor.py
- 状态管理: app/core/database.py, app/checkpoint_sqlite.py

## 7 个 Agent
1. supervisor.py — 意图分类+任务调度
2. chat_agent.py — 对话交互
3. profile_agent.py — 用户画像处理
4. resource_agent.py — 学习资源生成
5. question_agent.py — 出题与批改
6. path_agent.py — 学习路径规划
7. evaluation_agent.py — 学习效果评估

## API 路由
- /api/auth/* — 注册/登录
- /api/chat/* — 对话
- /api/profile/* — 用户画像
- /api/assessment/* — 学习评估
- /api/bkt/* — 知识追踪
- /api/learning-path/* — 学习路径
- /api/resources/* — 学习资源
- /api/conversation/* — 会话管理
- /api/review/* — 复习管理

## 关键服务
- bkt_service.py: 贝叶斯知识追踪
- rag_service.py: RAG 检索增强生成
- spark_client.py: 讯飞星火 LLM
- knowledge_graph.py: 知识图谱

## 测试须知
- conftest.py 已 mock 数据库和 RateLimiter
- 测试不需要外部服务运行
- 但需要 Python 3.11+（当前 3.10.3 不兼容）
