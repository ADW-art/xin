# A3 学习系统 - 项目地图

## 技术栈
- 后端: Python FastAPI + SQLAlchemy + LangGraph + ChromaDB + Redis + MySQL
- 前端: Vue 3 + Vite + TypeScript + Element Plus + Pinia
- 基础设施: Docker Compose（MySQL/Redis/MinIO/ChromaDB）
- 构建: python venv + npm

## 目录结构
E:\code\claude-1\
├── CLAUDE.md                    # AI 治理规则（本文件）
├── Makefile                     # 统一构建入口
├── .github/workflows/ci.yml     # CI 流水线
└── a3-learning-system/
    ├── docker-compose.yml       # 基础设施
    ├── backend/
    │   ├── app/
    │   │   ├── main.py          # FastAPI 入口
    │   │   ├── config.py         # 配置
    │   │   ├── agents/          # 多智能体系统
    │   │   │   ├── supervisor.py     # 调度者
    │   │   │   ├── chat_agent.py
    │   │   │   ├── profile_agent.py
    │   │   │   ├── resource_agent.py
    │   │   │   ├── question_agent.py
    │   │   │   ├── path_agent.py
    │   │   │   └── evaluation_agent.py
    │   │   ├── api/             # API 路由
    │   │   ├── core/            # 基础设施
    │   │   │   ├── database.py      # 数据库（MySQL）
    │   │   │   ├── rate_limit.py    # Redis 限流
    │   │   │   └── security.py      # JWT
    │   │   ├── models/          # ORM 模型
    │   │   ├── services/        # 业务逻辑
    │   │   │   ├── bkt_service.py   # 知识追踪
    │   │   │   ├── rag_service.py   # RAG 检索
    │   │   │   ├── spark_client.py  # LLM 调用
    │   │   │   └── knowledge_graph.py
    │   │   └── scripts/         # 数据摄取
    │   ├── tests/               # pytest 测试
    │   │   ├── conftest.py      # 测试驾驭基础设施
    │   │   └── test_*.py        # 测试用例
    │   └── requirements.txt
    ├── frontend/
    │   ├── src/                # Vue 3 源码
    │   ├── package.json
    │   └── vite.config.ts
    └── docs/
        ├── ai/                 # AI 知识库
        └── kg_*.json           # 知识图谱

## 关键命令
- make test: 跑全部测试
- make dev: 启动开发环境
- make check: 项目完整性检查
- python -m pytest tests/ -v: 后端测试
- npm run test: 前端测试

## 关键依赖
- MySQL 需要运行（docker-compose up mysql）
- Redis 需要运行（docker-compose up redis）
- LLM 调用走讯飞星火（SparkClient）
- RAG 检索走 ChromaDB / FAISS
- 测试时数据库和 Redis 被 conftest.py mock 掉
