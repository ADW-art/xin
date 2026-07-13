# A3 Learning System

> 基于多智能体（LangGraph）+ 自适应学习（BKT + 知识图谱）+ RAG 的个性化学习系统

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.4+-green.svg)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](#)

## ✨ 项目亮点

- **🤖 多智能体协同**：11 个 LangGraph 节点 + 6 个专职 Agent，Supervisor 智能调度
- **📊 自适应学习**：自研 BKT（贝叶斯知识追踪）内核 + 知识图谱拓扑排序
- **🔍 企业级 RAG**：BGE-M3 向量 + BGE-Reranker 重排 + 4 路混合检索
- **🌱 开箱即用**：内置 Python 知识种子，clone 后**无需任何操作**即可体验
- **🎯 完整路径规划**：从知识图谱 → 评估 → 个性化学习路径 → 资源推荐

## 🚀 5 分钟快速开始

### 0. 准备环境

- **Python 3.11+** （[下载](https://www.python.org/downloads/)）
- **Node.js 18+** （[下载](https://nodejs.org/)）
- **Docker Desktop** （[下载](https://www.docker.com/products/docker-desktop/)，用于 MySQL/Redis/MinIO/ChromaDB）
- **DeepSeek API Key** （[注册](https://platform.deepseek.com)，新用户有免费额度）

### 1. 克隆并启动依赖

```bash
git clone https://github.com/ADW-art/xin.git
cd xin/a3-learning-system
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-your-real-key
docker-compose up -d
```

### 2. 启动后端

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

> 🎉 **首次启动会自动加载 2496 条 Python 知识种子**，无需任何操作！

### 3. 启动前端

```bash
# 另开一个终端
cd frontend
npm install
npm run dev
```

### 4. 访问

打开浏览器：**http://localhost:5173** 🎉

## 🌱 种子数据说明

仓库内置了 **Python 课程种子数据**（约 2500 条，1.25 MB），用于新人开箱即用。

- 首次启动后端时自动加载到 ChromaDB
- 仅当知识库为空时加载，已有数据时跳过
- 数据来源：主人的治理知识图谱 + 精选 Python 文档
- 失效条件：升级 BGE-M3 模型后需要重新生成（`python scripts/export_python_seed.py`）

## 📖 详细文档

- 📘 [SETUP_GUIDE.md](SETUP_GUIDE.md) - 完整安装/部署指南
- 🏗️ [docs/项目详细介绍_PPT素材.md](docs/项目详细介绍_PPT素材.md) - 项目架构详解
- 🐛 [docs/P0_P1修复清单.md](docs/P0_P1修复清单.md) - 已修复问题列表
- 📊 [docs/RAG设计思路详解.md](docs/RAG设计思路详解.md) - RAG 检索实现细节

## 🛠️ 项目结构

```
a3-learning-system/
├── backend/                    # FastAPI + LangGraph 后端
│   ├── app/
│   │   ├── agents/            # 多智能体（supervisor, resource_agent, ...）
│   │   ├── api/               # REST 路由
│   │   ├── services/          # RAG, BKT, 知识图谱
│   │   └── core/              # 数据库, 配置, 中间件
│   ├── scripts/               # 运维/数据脚本
│   │   ├── load_seed_data.py          # 种子加载 (启动自动调)
│   │   ├── export_python_seed.py      # 种子导出 (主人本地用)
│   │   ├── ingest_curated_kb.py       # 知识图谱入库
│   │   ├── ingest_course.py           # 课程入库
│   │   ├── start_uvicorn_safe.ps1     # 安全启动 uvicorn
│   │   └── health_check.ps1           # 健康检查
│   ├── seed_data/             # ⭐ 种子数据 (入仓)
│   │   ├── python_seed.jsonl.gz       # 2496 条 Python 知识
│   │   ├── VERSION.json               # 生成元信息
│   │   └── README.md
│   └── requirements.txt
├── frontend/                   # Vue 3 + Vite 前端
│   ├── src/
│   │   ├── views/             # 页面
│   │   ├── components/        # 组件
│   │   └── api/               # API 调用
│   └── package.json
├── docs/                       # 设计文档 + 知识图谱
├── docker-compose.yml          # MySQL + Redis + MinIO + ChromaDB
├── SETUP_GUIDE.md             # 详细安装指南
└── README.md                  # ← 你在这里
```

## 🧪 常见问题

### Q: 启动后 ChromaDB 是空的？
**A: 应该不会！** 启动时自动加载种子数据。如果失败，查看后端日志：
```bash
# 手动重试
cd backend && python scripts/load_seed_data.py --force
```

### Q: 端口冲突？
A: 修改 `docker-compose.yml` 和后端启动端口（默认 8001）。

### Q: 怎么切换 LLM 提供商？
A: 修改 `backend/.env` 的 `DEEPSEEK_API_KEY` 等环境变量。

### Q: BGE 模型下载太慢？
A: 设置 `HF_ENDPOINT=https://hf-mirror.com`（已默认）

## 📜 License

MIT

---

🎉 **如果这个项目帮到主人，请点个 ⭐ Star！**
