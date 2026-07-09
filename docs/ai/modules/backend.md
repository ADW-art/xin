# 后端模块 — FastAPI
## 位置
a3-learning-system/backend/app/
## 入口
main.py — FastAPI 应用，注册所有 router 和中间件
## 目录结构
app/
├── main.py                  # 应用入口
├── config.py                # 配置（讯飞/MySQL/Redis 等）
├── checkpoint_sqlite.py     # SQLite checkpoint（Agent 状态持久化）
├── agents/                  # 多智能体系统
├── api/                     # API 路由
├── core/                    # 基础设施（数据库/限流/安全）
├── models/                  # ORM 模型
├── schemas/                 # Pydantic 模型
├── services/                # 业务逻辑
├── utils/                   # 工具函数
└── scripts/                 # 数据摄取脚本
## 依赖
- MySQL (docker-compose)
- Redis (docker-compose)
- ChromaDB (docker-compose)
- MinIO (docker-compose)
- 讯飞星火 LLM API
## 关键配置
- config.py 中 Settings 类，从 .env 文件读取
- MySQL 默认 localhost:3306, a3_learning 数据库
- Redis 默认 localhost:6379
- 讯飞星火有 4 个配置项（app_id, api_key, api_secret, app_password）
