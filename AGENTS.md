# A3 项目技术蓝图 (Codex 自动加载)

> **赛题**: 基于大模型的个性化资源生成与学习多智能体系统开发
> **出题方**: 科大讯飞 | **截止**: 2026-06-30 15:00
> **仓库**: ADW-art/xin | **本地路径**: E:\code\Codex-1

---

## 一、项目当前状态（2026-06-07 更新）

### 整体进度
| 层面 | 完成度 | 评价 |
|------|:--:|------|
| 后端 Agent+服务 | **95%** | 超出省一标准：BKT知识追踪 + 知识图谱拓扑排序 + 混合检索(RRF+CrossEncoder) 三件自研算法 |
| 后端 API+模型 | **95%** | 8个路由模块、7张ORM表、JWT认证全部就绪 |
| 前端页面骨架 | **70%** | 7个页面全部存在，SSE流式对话可用，但数据层薄弱 |
| 前端 Stores/API | **25%** | 只有 chat.ts。user.ts 和 learning.ts 缺失，API 封装散落 |
| 基础设施 | **100%** | MySQL+Redis+MinIO+ChromaDB 全部 Docker 运行中 |
| 知识库内容 | **5%** | RAG 检索架构完美但未注入教材 |
| 测试 | **0%** | 完全空白 |
| 比赛文档 | **0%** | 全部未启动 |

### 当前服务状态
```
Docker: a3-mysql(UP)  a3-redis(UP)  a3-minio(UP)  a3-chromadb(UP)
.env:   已配置讯飞星火 3 个 Key，MySQL 端口 3307
```

### 后端已实现的核心亮点
| 模块 | 说明 |
|------|------|
| **混合检索 (rag_service.py)** | FAISS 稠密 + BM25 稀疏 + RRF 融合 + BGE-Reranker 精排，企业级架构 |
| **BKT 追踪 (bkt_service.py)** | 贝叶斯四参数模型 (P(L0)/P(T)/P(G)/P(S))，自适应难度调节 |
| **知识图谱 (knowledge_graph.py)** | TF-IDF 知识点提取 → 共现分析 → DAG 拓扑排序 → 学习路径生成 |
| **复习调度 (review_scheduler.py)** | 艾宾浩斯遗忘曲线 + 间隔递增复习 (Spaced Repetition) |
| **文档解析 (document_parser.py)** | PDF (pdfplumber+PaddleOCR) + Word + Markdown 全格式 |
| **FAISS 多子索引 (faiss_client.py)** | 按学科分索引，路由+懒加载 |

### 前端当前状态（逐个视图）
| 视图 | 完成度 | 问题 |
|------|:--:|------|
| Login.vue | 90% | 功能可用 |
| Dashboard.vue | 40% | **全部硬编码假数据**，统计/雷达图/进度条数据固定 |
| ChatView.vue | 85% | SSE 流式+Agent 切换正常，缺历史侧栏 |
| ProfileView.vue | 80% | 6 维展示+编辑可用 |
| ResourceView.vue | 40% | 只有列表，**无详情页**，无 MindMap 渲染 |
| AssessmentView.vue | 35% | **环形图数据硬编码**，仅为 Markdown 文本 |
| LearningPathView.vue | 25% | 仅 Markdown 渲染，**vue-flow 已装但未使用**，无 DAG 图 |

### 关键缺失
- ❌ `stores/user.ts` 不存在 — 登录状态无集中管理
- ❌ `stores/learning.ts` 不存在
- ❌ `api/*.ts` 只有 index.ts 和 chat.ts — auth/profile/resource 封装全部缺失
- ❌ MindMap.vue 组件不存在 — markmap 已装但未创建组件
- ❌ StreamingText.vue 不存在 — 流式打字效果未实现
- ❌ Resource 详情页不存在 — 无法查看生成的思维导图/代码/文档
- ❌ RAG 知识库为空 — 没有注入任何教材

## 二、技术栈总表

### 核心框架
| 层 | 技术 | 版本要求 | 选型理由 |
|------|------|------|------|
| 前端 | Vue3 + TypeScript + Vite | Vue 3.4+, Vite 5+ | 用户已会，生态成熟 |
| UI库 | Element Plus | 2.x | 中文友好，组件丰富 |
| 状态管理 | Pinia | 2.x | Vue3 官方推荐 |
| 后端 | Python FastAPI | 0.110+ | 异步支持好，SSE原生支持 |
| AI编排 | LangGraph | 0.2+ | 状态图可视化是答辩得分点，支持SSE流式 |
| 大模型 | 讯飞星火API | 最新 | 赛题硬约束，必须用讯飞 |
| 关系数据库 | MySQL | 8.0 | 用户画像、学习记录等结构化数据 |
| 向量数据库 | ChromaDB | 0.5+ | 轻量、Python原生、免费本地部署 |
| 缓存 | Redis | 7.x | 会话管理、热数据缓存 |
| 对象存储 | MinIO | latest | 资源文件存储（文档/图片/视频） |
| Embedding | BGE-M3 + BGE-Reranker-v2 | bge-m3 / reranker-v2-m3 | 稠密+稀疏双向量，CrossEncoder精排 |
| 部署 | Docker + Docker Compose | latest | 一键启动所有服务 |

### Python 依赖清单
```
# 核心框架
fastapi==0.115.0
uvicorn[standard]==0.30.0
pydantic==2.9.0
python-multipart==0.0.12

# AI / Agent
langgraph>=0.2.20,<0.3
langchain==0.3.0
langchain-community==0.3.0
websocket-client==1.8.0        # 讯飞星火用WebSocket协议

# 数据库
sqlalchemy==2.0.35
asyncmy==0.2.9                 # MySQL异步驱动
chromadb==0.5.20
redis==5.1.0
pymysql==1.1.1

# 向量 / Embedding
sentence-transformers==3.1.0   # BGE模型推理
 torch>=2.0.0                   # PyTorch（BGE依赖）

# 认证
python-jose[cryptography]==3.3.0   # JWT
passlib[bcrypt]==1.7.4

# 工具
httpx==0.27.0                  # 异步HTTP客户端
aiofiles==24.1.0               # 异步文件操作
python-docx==1.1.0             # Word文档生成
markdown==3.7                  # Markdown处理
Pillow==10.4.0                 # 图片处理
```

### Node 依赖清单
```
# 前端
vue@3.4+
element-plus@2.8+
pinia@2.2+
axios@1.7+
vue-router@4.4+
marked@14+                     # Markdown渲染
markmap/markmap@0.17+          # 思维导图渲染
echarts@5.5+                   # 图表（雷达图、学习曲线）
@vue-flow/core@1.40+           # 学习路径DAG可视化
dayjs@1.11+                    # 日期处理
```

---

## 三、项目目录结构

```
a3-learning-system/                          # 项目根目录
├── docker-compose.yml                       # 一键启动 MySQL+Redis+MinIO+ChromaDB
├── .env                                     # 已配置讯飞Key + MySQL端口3307
├── .gitignore
│
├── backend/                                 # Python FastAPI 后端
│   ├── requirements.txt                     # 28个依赖包，与AGENTS.md一致
│   ├── app/
│   │   ├── main.py                          # FastAPI入口 + CORS + 8路由注册
│   │   ├── config.py                        # pydantic-settings 读 .env
│   │   ├── dependencies.py                  # SparkClient + LangGraph 图单例
│   │   │
│   │   ├── api/                             # ✅ 8个路由模块全部就绪
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                      # 注册/登录/me (JWT)
│   │   │   ├── chat.py                      # SSE流式对话（核心）+ 线程桥接
│   │   │   ├── profile.py                   # 画像CRUD
│   │   │   ├── resources.py                 # 资源列表+详情
│   │   │   ├── assessment.py                # 答题提交+记录+报告
│   │   │   ├── learning_path.py             # 路径查询
│   │   │   ├── conversation.py              # 对话历史
│   │   │   └── admin.py                     # 教材上传 + 知识库统计
│   │   │
│   │   ├── agents/                          # LangGraph 6 Agent ✅
│   │   │   ├── __init__.py
│   │   │   ├── supervisor.py                # 调度Agent（意图分类→路由）
│   │   │   ├── state.py                     # AgentState 共享状态定义
│   │   │   ├── profile_agent.py             # 画像Agent（6维对话采集+MySQL持久化）
│   │   │   ├── resource_agent.py            # 资源Agent（5种资源+RAG检索注入）
│   │   │   ├── question_agent.py            # 出题Agent（BKT自适应难度+题库检索）
│   │   │   ├── path_agent.py                # 路径Agent（KG拓扑+艾宾浩斯复习）
│   │   │   ├── evaluation_agent.py          # 评估Agent（6维评估+BKT数据）
│   │   │   └── core/                        # Agent核心（空目录，预留）
│   │   │
│   │   ├── models/                          # ORM模型 ✅ 7张表
│   │   │   ├── __init__.py
│   │   │   ├── user.py                      # 用户表
│   │   │   ├── profile.py                   # 学习画像表（6维+JSON字段）
│   │   │   ├── resource.py                  # 学习资源表
│   │   │   ├── assessment.py                # 评估报告表
│   │   │   ├── learning_path.py             # 学习路径表
│   │   │   ├── conversation.py              # 对话历史表
│   │   │   └── answer_record.py             # 答题记录表
│   │   │
│   │   ├── schemas/                         # Pydantic 请求/响应 ✅
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                      # RegisterRequest/LoginRequest/TokenResponse
│   │   │   ├── profile.py                   # ProfileUpdate/ProfileResponse
│   │   │   ├── resource.py                  # ResourceListResponse/DetailResponse
│   │   │   ├── assessment.py                # AssessmentResponse
│   │   │   └── path.py                      # PathResponse
│   │   │
│   │   ├── services/                        # 业务服务层 ✅
│   │   │   ├── __init__.py
│   │   │   ├── spark_client.py              # 讯飞星火WS客户端(HMAC签名+流式/同步双模式)
│   │   │   ├── rag_service.py               # 混合检索(FAISS稠密+BM25稀疏+RRF融合+CrossEncoder精排)
│   │   │   ├── bkt_service.py               # 贝叶斯知识追踪(BKT四参数模型)
│   │   │   ├── knowledge_graph.py           # 知识点图谱+拓扑排序+时间估算
│   │   │   ├── review_scheduler.py          # 艾宾浩斯遗忘曲线复习调度
│   │   │   ├── faiss_client.py              # FAISS 多子索引管理(按学科分)
│   │   │   └── document_parser.py           # 文档解析(PDF+OCR+Word+Markdown)
│   │   │
│   │   ├── core/                            # 核心基础设施 ✅
│   │   │   ├── __init__.py
│   │   │   ├── database.py                  # SQLAlchemy引擎+会话工厂
│   │   │   ├── chroma_client.py             # ChromaDB HTTP客户端(单例+集合缓存)
│   │   │   └── security.py                  # JWT+bcrypt密码哈希
│   │   │
│   │   └── scripts/                         # 知识库素材脚本
│   │       └── knowledge_materials/          # 教材/题库文件目录
│   │
│   └── tests/                               # ❌ 测试目录为空
│
├── frontend/                                # Vue3 + TypeScript 前端
│   ├── package.json                         # 14个依赖包
│   ├── vite.config.ts
│   ├── index.html
│   ├── src/
│   │   ├── main.ts                          # Vue3入口(Pinia+Router+ElementPlus全局图标)
│   │   ├── App.vue                          # 纯 <router-view/>
│   │   ├── router/index.ts                  # 7页面路由(懒加载)
│   │   ├── stores/                          # Pinia状态管理
│   │   │   ├── chat.ts                      # ✅ 对话状态(消息列表+流式+Agent切换)
│   │   │   ├── user.ts                      # ❌ 不存在
│   │   │   └── learning.ts                  # ❌ 不存在
│   │   ├── api/                             # 前端API封装
│   │   │   ├── index.ts                     # ✅ axios实例(JWT拦截器+401跳转)
│   │   │   ├── chat.ts                      # ✅ SSE流式请求(fetch手动解析)
│   │   │   ├── auth.ts                      # ❌ 不存在
│   │   │   ├── profile.ts                   # ❌ 不存在
│   │   │   └── resource.ts                  # ❌ 不存在
│   │   ├── views/                           # 页面组件 (7个全部存在)
│   │   │   ├── Login.vue                    # 登录/注册 (功能可用)
│   │   │   ├── Dashboard.vue                # ⚠️ 全部硬编码假数据
│   │   │   ├── ChatView.vue                 # SSE流式对话+Agent切换 (核心可用)
│   │   │   ├── ProfileView.vue              # 6维画像展示+编辑
│   │   │   ├── ResourceView.vue             # ⚠️ 仅有列表无详情
│   │   │   ├── AssessmentView.vue           # ⚠️ 环形图数据硬编码
│   │   │   └── LearningPathView.vue         # ⚠️ 仅Markdown无DAG图
│   │   ├── components/
│   │   │   ├── chat/
│   │   │   │   ├── ChatMessage.vue          # ✅ Markdown渲染消息气泡
│   │   │   │   ├── ChatInput.vue            # ✅ 输入框(Enter发送/Shift+Enter换行)
│   │   │   │   └── StreamingText.vue        # ❌ 不存在
│   │   │   ├── resource/
│   │   │   │   ├── ResourceCard.vue         # ❌ 不存在
│   │   │   │   └── MindMap.vue              # ❌ 不存在(markmap已装但未创建)
│   │   │   ├── assessment/
│   │   │   │   ├── RadarChart.vue           # ❌ 不存在
│   │   │   │   └── ScoreBoard.vue           # ❌ 不存在
│   │   │   └── common/
│   │   │       └── AppLayout.vue            # ✅ 侧边栏+顶栏布局
│   │   └── styles/
│   │       └── global.css                   # ✅ 完整设计系统(CSS变量+动画)
│   └── public/
│
└── docs/                                    # 项目文档
    ├── 操作手册.md                           # Git/Docker/开发操作速查
    ├── RAG设计思路详解.md                    # RAG 从概念到实现完整讲解
    ├── 教材台账_72本完整目录.md              # 知识库建设参考清单
    ├── knowledge_graph.json                  # 知识图谱数据
    ├── rag_evaluation_report.json            # RAG 评测数据
    ├── 需求分析文档.md                       (待写 - P3)
    ├── 技术设计文档.md                       (待写 - P3)
    ├── 测试报告.md                           (待写 - P3)
    └── 演示脚本.md                           (待写 - P3)
```

---

## 四、数据库设计

### MySQL 表结构

```sql
-- 用户表
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nickname VARCHAR(100),
    avatar_url VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 学习画像表（6维+核心数据）
CREATE TABLE learning_profiles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT UNIQUE NOT NULL,
    knowledge_base JSON,           -- 知识点掌握度 {"Python": 60, "数学": 70}
    cognitive_style VARCHAR(20),   -- visual/auditory/kinesthetic/reading
    learning_goal VARCHAR(50),     -- exam/skill/career/interest
    weekly_hours DECIMAL(4,1),     -- 每周可投入时间
    error_patterns JSON,           -- 易错模式 [{"type": "confusion", "concepts": ["list","tuple"]}]
    preferred_resource_type VARCHAR(20), -- video/text/code/interactive
    dimension_scores JSON,         -- 各维度量化分数 {"knowledge": 55, "logic": 70, ...}
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 对话历史表
CREATE TABLE conversations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    agent_type VARCHAR(30),        -- supervisor/profile/resource/question/path/evaluation
    role ENUM('user', 'assistant', 'system'),
    content TEXT NOT NULL,
    metadata JSON,                 -- 附加信息（token数、耗时等）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_user_time (user_id, created_at)
);

-- 学习资源表
CREATE TABLE resources (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    resource_type ENUM('document', 'mindmap', 'question_set', 'video_script', 'code_example'),
    title VARCHAR(200) NOT NULL,
    content TEXT,
    file_url VARCHAR(500),         -- MinIO文件地址
    knowledge_points JSON,         -- 关联知识点 ["Python基础", "list操作"]
    difficulty_level TINYINT,      -- 1-5 难度等级
    generated_by VARCHAR(30),      -- 生成的Agent名称
    feedback_score TINYINT,        -- 用户评分 1-5
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_user_type (user_id, resource_type)
);

-- 答题记录表
CREATE TABLE answer_records (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    question_id INT NOT NULL,
    user_answer TEXT,
    is_correct BOOLEAN,
    time_spent INT,                -- 答题用时（秒）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_user_question (user_id, question_id)
);

-- 学习路径表
CREATE TABLE learning_paths (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    path_data JSON,                -- DAG结构的路径数据
    current_node INT,              -- 当前所在节点序号
    status ENUM('active', 'completed', 'paused'),
    started_at DATETIME,
    completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 评估报告表
CREATE TABLE assessment_reports (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    report_type VARCHAR(30),       -- diagnostic/progress/final
    report_data JSON,              -- 完整报告结构
    dimension_scores JSON,         -- 各维度分数
    suggestions JSON,              -- 改进建议列表
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_user_type (user_id, report_type)
);
```

### ChromaDB 集合设计（实际使用）

| 集合名 | 存储内容 | Embedding模型 | 用途 |
|------|------|------|------|
| `knowledge_base` | 教材/课件文本切片 | BGE-M3 (dense) | RAG知识检索 |
| `exercise_bank` | 题库题目+答案+解析 | BGE-M3 | 相似题检索 |

> 注：Embedding 实际使用 BAAI/bge-m3（配置中默认值），重排序使用 BAAI/bge-reranker-v2-m3。
> 向量索引优先使用 FAISS 多子索引（按学科分），ChromaDB 作为降级方案。

### Redis 键设计

```
# 会话管理
session:{session_id}           → JSON   (TTL: 24h)

# JWT黑名单（登出后失效）
blacklist:{jti}                → "1"    (TTL: token过期时间)

# 用户对话上下文缓存（最近N轮）
chat_context:{user_id}         → JSON   (TTL: 1h)

# Agent状态缓存（LangGraph checkpoint）
checkpoint:{thread_id}         → JSON   (TTL: 24h)

# 资源生成队列（异步任务）
resource_queue                 → List   (FIFO队列)
```

---

## 五、多智能体架构设计（LangGraph）

### State 定义（实际代码，`agents/state.py`）

```python
from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # 消息历史（LangGraph自动追加）
    current_agent: str                                     # 当前激活Agent标识
    next_agent: Optional[str]                              # Supervisor的路由决策
    user_profile: Optional[dict]                           # 6维学习画像（从MySQL加载）
    context: dict                                          # 当前对话上下文 {"topic": "...", ...}
    agent_outputs: dict                                    # 各Agent输出缓存（避免重复生成）
    stream_buffer: str                                     # SSE流式输出缓冲区
    user_id: int                                           # 当前用户ID（从JWT解析）
```

### Supervisor（调度Agent）路由逻辑

```
用户输入 → Supervisor理解意图 → 路由决策:

意图分类：
├── 自我介绍/学习目标/时间 → profile_agent（画像Agent）
├── 想学XX/生成资料/XX是什么 → resource_agent（资源Agent）
├── 做题/测试/来点题目 → question_agent（出题Agent）
├── 学习计划/下一步学什么 → path_agent（路径Agent）
├── 评估/我学得怎样/报告 → evaluation_agent（评估Agent）
└── 闲聊/未知 → supervisor直接回复

决策实现：
- 使用讯飞星火API + 结构化提示词做意图分类
- 返回JSON: {"intent": "learn_resource", "params": {"topic": "Python", "level": "beginner"}}
- 根据intent路由到对应Agent节点
```

### LangGraph 图结构

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

def build_graph():
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("profile_agent", profile_agent_node)
    workflow.add_node("resource_agent", resource_agent_node)
    workflow.add_node("question_agent", question_agent_node)
    workflow.add_node("path_agent", path_agent_node)
    workflow.add_node("evaluation_agent", evaluation_agent_node)

    # 入口
    workflow.set_entry_point("supervisor")

    # Supervisor根据意图路由到不同Agent
    workflow.add_conditional_edges(
        "supervisor",
        router_function,  # 返回 "profile_agent" | "resource_agent" | ...
        {
            "profile_agent": "profile_agent",
            "resource_agent": "resource_agent",
            "question_agent": "question_agent",
            "path_agent": "path_agent",
            "evaluation_agent": "evaluation_agent",
            "END": END,
        }
    )

    # 所有Agent执行完后回到Supervisor
    workflow.add_edge("profile_agent", "supervisor")
    workflow.add_edge("resource_agent", "supervisor")
    workflow.add_edge("question_agent", "supervisor")
    workflow.add_edge("path_agent", "supervisor")
    workflow.add_edge("evaluation_agent", "supervisor")

    # 编译（带记忆checkpoint）
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)
    return app
```

### 各Agent的Prompt设计

#### Supervisor（调度Agent）
```
你是一个学习系统的调度中枢。根据用户输入，判断意图并路由到合适的Agent。

意图类型：
1. "profile" - 用户介绍自己的学习背景、目标、时间安排、偏好
2. "resource" - 用户想学习某个知识点、需要学习资料
3. "question" - 用户想做题、测试、评估当前水平
4. "path" - 用户想了解学习路线、下一步计划
5. "evaluation" - 用户想查看学习报告、评估结果
6. "chat" - 普通闲聊（不需要路由）

返回JSON格式：{"intent": "...", "params": {...}}
```

#### Profile Agent（画像Agent）
```
你是一个学习画像采集专家。通过对话式交互，逐步了解学生的6个维度：

1. 知识基础 - "你之前学过哪些相关内容？自评掌握程度1-10分"
2. 认知风格 - "你更喜欢看视频学、看书学、还是动手做项目学？"
3. 学习目标 - "你学习这个是为了考试、找工作、还是兴趣？"
4. 时间投入 - "每周大概能投入多少小时学习？"
5. 易错模式 - 从答题记录中分析容易出错的模式
6. 偏好资源类型 - "你喜欢看文档、思维导图、还是视频？"

每次对话只采集1-2个维度，不要一次问太多。采集完后生成结构化画像JSON。
```

#### Resource Agent（资源生成Agent）
```
你是一个学习资源生成专家。根据学生的学习画像和当前知识点，生成个性化学习资源。

资源类型：
1. 知识文档 - 结构化的学习笔记，Markdown格式
2. 思维导图 - Markdown标题层级结构（前端用markmap渲染）
3. 练习题 - 3-5道选择题/填空题，包含答案和解析
4. 视频脚本 - 5分钟讲解脚本，分镜头描述
5. 代码案例 - 可执行的Python代码，包含注释

要求：
- 难度匹配学生的知识基础
- 风格匹配学生的认知风格（视觉型→多图表，动手型→多代码示例）
- 生成后自动存入资源库，关联到对应知识点
```

#### Question Agent（出题Agent）
```
你是一个自适应出题专家。根据学生画像和当前学习阶段，生成合适的题目。

出题规则：
- 初始诊断测试：覆盖范围广，难度适中
- 学习后测试：聚焦刚学的知识点
- 难度自适应：连续答对2题→升难度，答错→降难度
- 题型混合：选择题60% + 填空题20% + 代码题20%
- 每题包含：题目、选项、答案、解析、关联知识点
```

#### Path Agent（路径规划Agent）
```
你是一个学习路径规划专家。根据学生画像和知识图谱，规划最优学习路线。

规划原则：
1. 前置知识必须先学（拓扑排序）
2. 难度递增（从基础到进阶）
3. 考虑学生的时间投入（每周X小时 → 计算需要几周）
4. 穿插复习节点（遗忘曲线复习点）
5. 动态调整（根据评估结果调整后续路径）

输出：DAG结构的路径JSON（节点=知识单元，边=学习顺序，权重=建议时间）
```

#### Evaluation Agent（评估Agent）
```
你是一个学习效果评估专家。根据学生的答题记录和行为数据，生成多维度评估报告。

评估维度：
1. 知识掌握度（基于答题正确率）
2. 学习速度（单位时间掌握的知识点数）
3. 薄弱环节（高频错误知识点）
4. 进步趋势（与上次评估对比）
5. 学习投入度（活跃天数、日均学习时长）
6. 推荐策略（基于评估结果的改进建议）

输出：包含6维雷达图数据 + 文字建议的JSON
```

---

## 六、讯飞星火API集成

### 认证方式
- 协议：WebSocket
- 鉴权：通过URL参数传递 `authorization`（API Key生成签名）
- 文档：https://www.xfyun.cn/doc/spark/Web.html

### Python客户端封装（关键代码骨架）

```python
# backend/app/services/spark_client.py
import json
import websocket
import ssl
import threading
from datetime import datetime
from urllib.parse import urlencode
import hmac
import hashlib
import base64
from typing import Generator

class SparkClient:
    """讯飞星火大模型 WebSocket 客户端"""

    SPARK_URL = "wss://spark-api.xf-yun.com/v4.0/chat"
    DOMAIN = "4.0Ultra"  # 根据实际模型版本调整

    def __init__(self, app_id: str, api_key: str, api_secret: str):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret

    def _get_auth_url(self) -> str:
        """生成带鉴权的WebSocket URL"""
        host = "spark-api.xf-yun.com"
        path = "/v4.0/chat"
        now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        signature_origin = f"host: {host}\ndate: {now}\nGET {path} HTTP/1.1"
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode(),
                signature_origin.encode(),
                hashlib.sha256
            ).digest()
        ).decode()
        authorization = base64.b64encode(
            f"api_key=\"{self.api_key}\", algorithm=\"hmac-sha256\", headers=\"host date request-line\", signature=\"{signature}\"".encode()
        ).decode()
        params = {
            "authorization": authorization,
            "date": now,
            "host": host,
        }
        return f"{self.SPARK_URL}?{urlencode(params)}"

    def chat_stream(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 4096) -> Generator[str, None, None]:
        """流式对话，返回Generator（逐token yield）"""
        url = self._get_auth_url()
        ws = websocket.create_connection(url, sslopt={"cert_reqs": ssl.CERT_NONE})

        request_data = {
            "header": {"app_id": self.app_id, "uid": "user_xxx"},
            "parameter": {
                "chat": {
                    "domain": self.DOMAIN,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
            },
            "payload": {
                "message": {
                    "text": messages  # [{"role": "user", "content": "..."}, ...]
                }
            },
        }
        ws.send(json.dumps(request_data))

        while True:
            response = json.loads(ws.recv())
            code = response["header"]["code"]
            if code != 0:
                raise Exception(f"讯飞API错误: {response['header']['message']}")

            choices = response["payload"]["choices"]
            status = choices["status"]
            content = choices["text"][0]["content"]
            yield content  # 逐段yield，上层做SSE推送

            if status == 2:  # 2表示结束
                break
        ws.close()
```

### 环境变量模板 (.env.example)

```env
# 讯飞星火
SPARK_APP_ID=your_app_id
SPARK_API_KEY=your_api_key
SPARK_API_SECRET=your_api_secret

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=a3_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=a3_learning

# Redis
REDIS_URL=redis://localhost:6379/0

# ChromaDB
CHROMA_PERSIST_DIR=./chroma_data

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# JWT
JWT_SECRET_KEY=your_secret_key_at_least_32_chars
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# BGE Embedding
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DEVICE=cpu   # 或 cuda（有GPU的话）
```

---

## 七、Docker Compose（一键启动基础设施）

```yaml
# docker-compose.yml（实际文件）
version: "3.8"
services:
  mysql:
    image: mysql:8.0
    container_name: a3-mysql
    environment:
      MYSQL_ROOT_PASSWORD: root123
      MYSQL_DATABASE: a3_learning
      MYSQL_USER: a3_user
      MYSQL_PASSWORD: a3_pass
    ports:
      - "3307:3306"          # 注意：宿主机3307→容器3306
    volumes:
      - mysql_data:/var/lib/mysql
      - ./backend/alembic/init.sql:/docker-entrypoint-initdb.d/init.sql

  redis:
    image: redis:7-alpine
    container_name: a3-redis
    ports:
      - "6379:6379"

  minio:
    image: minio/minio:latest
    container_name: a3-minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

  chromadb:
    image: chromadb/chroma:0.5.20
    container_name: a3-chromadb
    ports:
      - "8000:8000"
    volumes:
      - chroma_data:/chroma/chroma

volumes:
  mysql_data:
  minio_data:
  chroma_data:
```

**启动命令：**
```bash
docker-compose up -d
# 验证：docker-compose ps （4个服务都应该是Up状态）
```

---

## 八、API路由设计（已实现）

| 方法 | 路径 | 说明 | 认证 | 流式 |
|------|------|------|:--:|:--:|
| POST | `/api/auth/register` | 注册（返回JWT） | | |
| POST | `/api/auth/login` | 登录（返回JWT） | | |
| GET | `/api/auth/me` | 获取当前用户信息 | ✅ | |
| POST | `/api/chat/send` | 发送消息（核心接口） | 可选 | ✅ SSE |
| GET | `/api/chat/history` | 获取对话历史 | ✅ | |
| GET | `/api/profile/me` | 获取学习画像（无画像自动创建） | ✅ | |
| PUT | `/api/profile/me` | 更新学习画像 | ✅ | |
| GET | `/api/resources?type=&page=&size=` | 获取资源列表 | ✅ | |
| GET | `/api/resources/{id}` | 获取资源详情（含content） | ✅ | |
| POST | `/api/assessment/submit` | 提交答题结果 | ✅ | |
| GET | `/api/assessment/records` | 答题记录列表 | ✅ | |
| GET | `/api/assessment/reports` | 评估报告列表 | ✅ | |
| GET | `/api/assessment/reports/{id}` | 评估报告详情 | ✅ | |
| GET | `/api/path/current` | 获取当前活跃学习路径 | ✅ | |
| POST | `/api/admin/upload` | 上传教材（PDF/Word/MD）→入库 | ✅ | |
| GET | `/api/admin/stats` | 知识库统计 | ✅ | |
| GET | `/api/health` | 健康检查 | | |

### 待补充的接口
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/assessment/batch-submit` | 批量提交答题（支持完整测试流程） |
| PUT | `/api/path/current` | 更新学习路径节点（标记完成/暂停） |
| POST | `/api/resources/generate` | 手动触发资源生成 |

### SSE 流式对话响应格式

```
event: message
data: {"type": "text", "content": "我", "agent": "supervisor"}

event: message
data: {"type": "text", "content": "来", "agent": "supervisor"}

event: agent_switch
data: {"from": "supervisor", "to": "resource_agent", "reason": "生成学习资源"}

event: message
data: {"type": "text", "content": "正在为你生成Python基础学习资料...", "agent": "resource_agent"}

event: message
data: {"type": "resource", "resource_type": "mindmap", "url": "/api/resources/123?format=json"}

event: done
data: {"total_tokens": 1234, "agents_used": ["supervisor", "resource_agent"]}
```

---

## 九、前端路由与组件树（实际状态）

### 路由设计（已实现）

```
/login                    → Login.vue           ✅ 登录注册页
/dashboard                → Dashboard.vue       ⚠️ 数据硬编码
/chat                     → ChatView.vue        ✅ SSE流式+Agent切换
/profile                  → ProfileView.vue     ✅ 6维展示+编辑
/resources                → ResourceView.vue    ⚠️ 仅列表
/assessment               → AssessmentView.vue  ⚠️ 数据硬编码
/learning-path            → LearningPathView.vue ⚠️ 无DAG图
```

### ChatView.vue 实际组件树

```
ChatView.vue
├── 消息列表（自动滚动）
│   ├── ChatMessage.vue     ✅ Markdown渲染（marked）
│   ├── Agent切换标签       ✅ Supervisor→资源Agent切换提示
│   └── StreamingText.vue   ❌ 未实现（内容直接append，无打字效果）
├── 空状态引导               ✅ 首次进入提示
└── ChatInput.vue           ✅ Enter发送/Shift+Enter换行

缺少：
- 左侧对话历史侧栏（API已就绪，前端未做）
- 右侧上下文面板（画像摘要/资源推荐）
- 思维导图内嵌渲染
- 资源卡片内嵌
```

### Pinia Store 实际状态

```typescript
// stores/chat.ts ✅ 已实现
interface ChatState {
  messages: ChatMessage[]
  isStreaming: boolean
  currentAgent: string
  // 方法：addUserMessage / startAssistantReply / appendToStreaming
  //       setAgentSwitch / finishAssistantReply / clearMessages
}

// stores/user.ts ❌ 未创建 — 需要包含token/userInfo/profile
// stores/learning.ts ❌ 未创建 — 需要包含resources/assessments/path
```

---

## 十、当前任务计划（6.7 - 6.30，23天）

> 基于 2026-06-07 代码审查结果制定。后端已超过省一标准，重点补齐前端数据层和比赛文档。

### P0 — 前端数据层补全（6.7 当天）

| # | 任务 | 优先级 | 预计 |
|------|------|:--:|------|
| 1 | 创建 `stores/user.ts` — JWT管理、用户信息、画像缓存 | 🔴 | 30min |
| 2 | 创建 `stores/learning.ts` — 资源列表、评估数据、路径状态 | 🔴 | 30min |
| 3 | 创建 `api/auth.ts` `api/profile.ts` `api/resource.ts` `api/assessment.ts` `api/path.ts` | 🔴 | 1h |
| 4 | 重构 Dashboard.vue — 从 API 拉真实数据，统计+雷达图动态化 | 🔴 | 1h |
| 5 | 重构 AssessmentView.vue — 环形图绑定评估报告真实数据 | 🔴 | 1h |
| 6 | 实现 MindMap.vue — markmap 渲染思维导图 | 🔴 | 1h |
| 7 | 实现 StreamingText.vue — 逐字打字机效果 | 🟡 | 30min |
| 8 | 实现 ResourceDetail 页 — 按类型渲染（文档/导图/代码/题目） | 🔴 | 1.5h |

### P1 — 前端体验闭环（6.8 - 6.10）

| # | 任务 | 预计 |
|------|------|------|
| 9 | 对话历史侧栏 — ChatView 左侧 ConversationList | 1h |
| 10 | LearningPathView DAG图 — vue-flow 渲染拓扑排序结果 | 2h |
| 11 | 资源评分反馈 — 用户对生成资源打分 | 0.5h |
| 12 | 全链路联调 — 注册→画像采集→对话→生成资源→评估→路径 | 2h |
| 13 | 注入知识库 — Python/数据结构教材→向量化入库→验证检索 | 2h |

### P2 — 加分特性（6.11 - 6.20）

| # | 任务 | 说明 |
|------|------|------|
| 14 | 评估测试闭环 | 前端出题→答题→自动批改→BKT更新→雷达图刷新 |
| 15 | 知识库管理界面 | 前端上传教材、查看入库状态 |
| 16 | Docker 部署化 | 前端 Dockerfile + 后端 Dockerfile + nginx 反代 |
| 17 | 安全加固 | 请求限流(middleware)、操作日志 |
| 18 | 响应式适配 | Dashboard/Profile 移动端适配 |

### P3 — 比赛文档（6.21 - 6.29）

| # | 文档 | 核心要点 |
|------|------|------|
| 19 | 需求分析文档 | 个性化学习痛点 → 6维画像 → 多Agent方案 |
| 20 | 技术设计文档 | 架构图 + BKT算法 + 知识图谱拓扑排序 + 混合检索架构 |
| 21 | 测试报告 | Agent准确率 + RAG检索精度 + SSE延迟 + 功能测试用例 |
| 22 | 演示视频 | 用户注册→画像采集→对话学习→资源生成→评估报告 全流程 |
| 23 | PPT制作 | 15页以内：背景/方案/创新点(BKT+KG+HybridRAG)/架构/演示/总结 |

### P4 — 提交（6.30）

- [ ] 08:00 最后检查
- [ ] 10:00 上传作品
- [ ] 14:00 确认提交成功
- [ ] 15:00 截止

---

**当前进度追踪方式：**
- 每完成一个任务，在对应的 `- [ ]` 前打勾改为 `- [x]`
- 任务完成顺序：P0 → P1 → P2 → P3，不跳跃

---

## 十一、给下一个Codex会话的启动指令

> 如果这是全新的Codex会话，请按以下步骤快速恢复：

```
1. 阅读本文件（AGENTS.md）- Codex 会自动加载
2. 运行 docker ps 确认基础设施是否运行（4个容器应全部Up）
3. 阅读"一、项目当前状态"了解整体进度
4. 阅读"十、当前任务计划"找到 P0-P3 待办事项
5. 根据 P0→P1→P2→P3 优先级顺序，从第一个未勾选的任务开始执行
```

**重要上下文：**
- 后端已完成 95%，质量很高。BKT+知识图谱+混合检索是三个自研算法亮点
- 前端页面骨架都已完成，当前重点是补数据层和缺失组件
- .env 已配置讯飞星火 Key，MySQL 端口 3307
- 启动方式：`docker-compose up -d` → `cd backend && uvicorn app.main:app --reload --port 8000` → `cd frontend && npm run dev`

---

## 十二、关键参考资源

| 资源 | 链接 |
|------|------|
| 讯飞星火API文档 | https://www.xfyun.cn/doc/spark/Web.html |
| LangGraph文档 | https://langchain-ai.github.io/langgraph/ |
| LangGraph Supervisor示例 | https://langchain-ai.github.io/langgraph/tutorials/multi_agent/agent_supervisor/ |
| ChromaDB文档 | https://docs.trychroma.com/ |
| FastAPI文档 | https://fastapi.tiangolo.com/ |
| Element Plus文档 | https://element-plus.org/ |
| 参考项目（2025二等奖） | https://github.com/zzzlip/langgraph-AI-interview-agent |
| BGE-M3模型 | https://huggingface.co/BAAI/bge-m3 |
| BGE-Reranker | https://huggingface.co/BAAI/bge-reranker-v2-m3 |
| markmap（思维导图） | https://markmap.js.org/ |
| Vue Flow（DAG图） | https://vueflow.dev/ |
| FAISS | https://github.com/facebookresearch/faiss |
| PaddleOCR | https://github.com/PaddlePaddle/PaddleOCR |
| BKT 理论参考 | Corbett & Anderson (1995), "Knowledge Tracing" |

---

## 附录A：快速启动脚本

```bash
# ===== 首次搭建（Windows PowerShell）=====

# 1. 进入项目目录
cd a3-learning-system

# 2. 启动基础设施（MySQL:3307, Redis, MinIO:9000/9001, ChromaDB:8000）
docker-compose up -d

# 3. 验证基础设施
docker ps  # 4个容器都应显示 Up

# 4. 后端
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 5. 前端（新终端）
cd frontend
npm install
npm run dev

# ===== 验证服务 =====
# 后端API文档: http://localhost:8000/docs
# 前端页面: http://localhost:5173
# MinIO控制台: http://localhost:9001
# 健康检查: curl http://localhost:8000/api/health
```

### 日常开发启动（基础设施已运行）

```bash
# 后端
cd a3-learning-system/backend
uvicorn app.main:app --reload --port 8000

# 前端（另一个终端）
cd a3-learning-system/frontend
npm run dev
```

---

## 附录B：settings.local.json 已配置权限

```json
{
  "permissions": {
    "allow": [
      "WebSearch",
      "Bash(git *)", "Bash(ssh *)", "Bash(ping *)",
      "Bash(nslookup *)", "Bash(netsh interface *)",
      "Bash(ipconfig *)", "Bash(gh *)",
      "Bash(python *)", "Bash(pip *)",
      "Bash(npm *)", "Bash(npx *)", "Bash(node *)",
      "Bash(docker *)", "Bash(curl *)",
      "Bash(mkdir *)", "Bash(rm *)", "Bash(cp *)", "Bash(mv *)",
      "WebFetch(domain:github.com)",
      "WebFetch(domain:www.xfyun.cn)",
      "WebFetch(domain:docs.trychroma.com)",
      "WebFetch(domain:langchain-ai.github.io)",
      "WebFetch(domain:python.langchain.com)",
      "WebFetch(domain:fastapi.tiangolo.com)",
      "WebFetch(domain:element-plus.org)",
      "WebFetch(domain:cn.vuejs.org)",
      "WebFetch(domain:www.cnsoftbei.com)"
    ]
  }
}
```

---

## 附录C：常见问题

**Q: 讯飞星火API调用失败？**
A: 检查 .env 中 3 个值：SPARK_APP_ID、SPARK_API_KEY、SPARK_API_SECRET。注意 API_SECRET ≠ API_KEY。

**Q: ChromaDB 连接失败？**
A: Docker chromadb 容器使用镜像 `chromadb/chroma:0.5.20`，端口 8000。`docker-compose up -d chromadb`

**Q: FAISS 导入失败？**
A: `pip install faiss-cpu`。FAISS 用于稠密向量检索，不可用时自动降级到 ChromaDB。

**Q: BGE 模型下载慢？**
A: 设置 HuggingFace 镜像：`export HF_ENDPOINT=https://hf-mirror.com`。首次运行会下载 BGE-M3 (~2GB) 和 BGE-Reranker (~1GB)。

**Q: LangGraph 图不执行？**
A: 检查 checkpointer (MemorySaver) 是否正确配置，每次调用需要传 `config={"configurable": {"thread_id": "..."}}`。

**Q: MySQL 连接失败？**
A: MySQL 端口映射为 3307→3306（不是默认的 3306），检查 .env 中 `MYSQL_PORT=3307`。

**Q: 前端 npm run dev 报错？**
A: 确保 `npm install` 已完成。Vite 默认端口 5173，需在 vite.config.ts 中配置代理到后端 8000。

---

> 📌 **这是项目的唯一真相源文件。任何技术决策、架构设计、配置信息都记录在此。**
> 每次完成阶段性任务后，更新第一部分的"项目当前状态"和第十部分的任务勾选。
