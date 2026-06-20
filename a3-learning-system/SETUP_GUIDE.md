# A3 学习系统 — 本地环境搭建指南

> 适用：从零开始，在 Windows/macOS/Linux 上运行完整项目

---

## 一、环境要求

| 工具 | 最低版本 | 用途 |
|------|:--:|------|
| Git | 2.0+ | 克隆仓库 |
| Docker + Docker Compose | 24.0+ | 运行 MySQL/Redis/MinIO/ChromaDB |
| Python | 3.10+ | 后端 FastAPI |
| Node.js | 18+ | 前端 Vue3 + Vite |
| pip | 23+ | Python 包管理 |
| npm | 9+ | 前端包管理 |

验证命令：
```bash
git --version       # >= 2.0
docker --version    # >= 24.0
python --version    # >= 3.10
node --version      # >= 18
```

---

## 二、克隆项目

```bash
git clone https://github.com/ADW-art/xin.git
cd xin/a3-learning-system
```

---

## 三、配置环境变量

项目根目录已有 `.env` 文件模板，**需要替换为自己的讯飞星火 API Key**：

```bash
# 编辑 .env 文件，修改以下 4 行（去讯飞官网申请：https://www.xfyun.cn/）
SPARK_APP_ID=你的APP_ID
SPARK_API_KEY=你的API_KEY
SPARK_API_SECRET=你的API_SECRET
SPARK_APP_PASSWORD=你的APP_PASSWORD
```

📌 **获取 API Key**：登录 [讯飞开放平台](https://console.xfyun.cn/) → 创建应用 → 选择"星火大模型" → 复制 APP_ID / API_KEY / API_SECRET / APP_PASSWORD。

其余配置项可保持默认值（MySQL/Redis/MinIO/ChromaDB 已与 docker-compose.yml 对齐）。

---

## 四、启动基础设施（Docker）

```bash
# 在项目根目录 a3-learning-system/ 下执行
docker-compose up -d
```

这会启动 4 个容器：

| 服务 | 容器名 | 宿主机端口 | 容器端口 |
|------|--------|:--:|:--:|
| MySQL 8.0 | a3-mysql | 3307 | 3306 |
| Redis 7 | a3-redis | 6379 | 6379 |
| MinIO | a3-minio | 9000/9001 | 9000/9001 |
| ChromaDB 0.5.20 | a3-chromadb | 8000 | 8000 |

验证：
```bash
docker ps  # 4个容器状态应全部为 Up
```

> 如果 Docker 未启动或报错，先确保 Docker Desktop 正在运行。

---

## 五、启动后端

### 5.1 创建 Python 虚拟环境

```bash
cd backend

# Windows
python -m venv venv
venv\Scripts\activate
```

### 5.2 安装依赖

```bash
pip install -r requirements.txt
```

> 首次安装会下载 PyTorch (~2GB)、sentence-transformers (~500MB)，请耐心等待。
> 如果 `torch` 安装失败（CUDA DLL 缺失），安装 CPU 版本：
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> ```

### 5.3 启动后端服务

```bash
# 在 backend/ 目录下
uvicorn app.main:app --reload --port 8001 --host 0.0.0.0
```

验证：
```bash
curl http://localhost:8001/api/health
# 应返回 {"status":"ok","version":"0.1.0"}
```

API 文档：打开浏览器访问 http://localhost:8001/docs

> ⚠️ **注意端口**：后端用 **8001**（不是 8000，8000 已被 ChromaDB 占用）

---

## 六、启动前端

打开**新的终端窗口**：

```bash
cd frontend
npm install
npm run dev
```

验证：打开浏览器访问 http://localhost:5173

首次访问会自动跳转到登录页 `/login`。

---

## 七、首次使用

### 7.1 注册账号

在登录页点击"没有账号？去注册"，或直接使用 API：

```bash
curl -X POST http://localhost:8001/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"test123456","nickname":"测试用户"}'
```

### 7.2 开始对话

1. 登录后进入 Dashboard → 点击"开始对话"
2. 输入"你好，我想学Python" → 系统会**先采集你的学习画像**（问你学过什么、目标是什么等）
3. 回答画像问题后，系统自动生成个性化学习内容

---

## 八、常见问题

### Q1: Docker 容器无法启动
```bash
# 检查端口占用
netstat -ano | grep 3307  # MySQL
netstat -ano | grep 6379  # Redis
netstat -ano | grep 9000  # MinIO
netstat -ano | grep 8000  # ChromaDB

# 重启 Docker 服务
docker-compose down
docker-compose up -d
```

### Q2: Python 依赖安装失败（Windows）
```bash
# 如果 sentence-transformers 安装失败，先安装 torch CPU 版本
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# 如果 bcrypt 编译失败
pip install bcrypt==4.0.1 --only-binary=:all:
```

### Q3: 前端 npm install 报错
```bash
# 清除缓存重试
npm cache clean --force
rm -rf node_modules package-lock.json
npm install
```

### Q4: 讯飞星火 API 调用失败
检查 `.env` 文件中 4 个 SPARK_* 配置是否正确：
- `SPARK_APP_ID` — 应用 ID
- `SPARK_API_KEY` — API Key
- `SPARK_API_SECRET` — API Secret（**不是 API Key！**）
- `SPARK_APP_PASSWORD` — 火花密钥（控制台 → 应用详情 → 火花密钥）

### Q5: 前端页面空白 / API 请求 404
确认：
1. 后端运行在 **8001** 端口（不是 8000）
2. 前端 Vite 代理配置正确（`vite.config.ts` 中 `/api` 代理到 `http://localhost:8001`）
3. 浏览器 F12 查看 Network 面板确认请求地址

### Q6: BGE 模型下载慢
.env 中已配置 `HF_ENDPOINT=https://hf-mirror.com`（国内镜像），首次启动会自动下载模型（~2GB）。如果仍然很慢，可以手动设置：
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

> BGE 模型下载失败不会阻塞服务启动，RAG 功能会降级为纯 LLM 模式。

---

## 九、项目结构速查

```
a3-learning-system/
├── docker-compose.yml          # Docker 基础设施
├── .env                        # 环境变量（需修改 API Key）
├── backend/                    # Python FastAPI 后端
│   ├── requirements.txt        # Python 依赖
│   ├── app/
│   │   ├── main.py             # FastAPI 入口
│   │   ├── agents/             # 6 个 Agent（Supervisor + 5 Worker）
│   │   ├── api/                # 10 个 API 路由
│   │   ├── services/           # BKT / RAG / 知识图谱 / 复习调度
│   │   └── models/             # ORM 数据模型
│   └── tests/
├── frontend/                   # Vue3 + TypeScript 前端
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── views/              # 10 个页面
│       ├── components/         # 消息/思维导图/资源卡片
│       ├── stores/             # Pinia 状态管理
│       └── api/                # 前端 API 封装
└── docs/                       # 项目文档
```

---

## 十、快速启动检查清单

- [ ] `docker ps` — 4 个容器全部 Up
- [ ] `curl http://localhost:8001/api/health` — 返回 `{"status":"ok"}`
- [ ] `curl http://localhost:5173` — 返回前端 HTML
- [ ] 浏览器打开 http://localhost:5173 — 显示登录页
- [ ] 注册新用户 → 登录 → Dashboard 加载
- [ ] 进入 AI 对话 → 发送"你好" — 收到流式回复
- [ ] 发送"我想学Python" — 先采集画像再生成内容
