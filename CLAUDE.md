# A3 项目技术蓝图 (Claude Code 自动加载)

> **赛题**: 基于大模型的个性化资源生成与学习多智能体系统开发
> **出题方**: 科大讯飞 | **截止**: 2026-06-30 15:00
> **仓库**: ADW-art/xin | **本地路径**: E:\code\claude-1

---

## 一、项目当前状态

| 状态项 | 详情 |
|------|------|
| 开发阶段 | 尚未开始编码，处于规划阶段 |
| 项目脚手架 | 未创建，代码目录不存在 |
| Docker | 未安装（用户需要先装 Docker Desktop） |
| 讯飞星火 API Key | 未获取（用户需要注册 https://www.xfyun.cn/） |
| settings.local.json | 已配置好所有权限 |

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
| Embedding | BGE中文模型 | bge-large-zh-v1.5 | 免费本地跑，中文效果好 |
| 部署 | Docker + Docker Compose | latest | 一键启动所有服务 |

### Python 依赖清单
```
# 核心框架
fastapi==0.115.0
uvicorn[standard]==0.30.0
pydantic==2.9.0
python-multipart==0.0.12

# AI / Agent
langgraph==0.2.0
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
a3-learning-system/                    # 项目根目录
├── docker-compose.yml                 # 一键启动所有基础设施
├── .env.example                       # 环境变量模板
├── .gitignore
│
├── backend/                           # Python FastAPI 后端
│   ├── requirements.txt
│   ├── alembic.ini                    # 数据库迁移配置
│   ├── alembic/
│   │   └── versions/                  # 迁移脚本
│   ├── app/
│   │   ├── main.py                    # FastAPI入口
│   │   ├── config.py                  # 配置管理（读.env）
│   │   ├── dependencies.py            # 依赖注入
│   │   │
│   │   ├── api/                       # API路由层
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                # 登录注册
│   │   │   ├── chat.py                # SSE流式对话（核心）
│   │   │   ├── profile.py             # 学习画像CRUD
│   │   │   ├── resource.py            # 资源管理
│   │   │   ├── assessment.py          # 评估报告
│   │   │   └── learning_path.py       # 学习路径
│   │   │
│   │   ├── agents/                    # LangGraph Agent层（核心）
│   │   │   ├── __init__.py
│   │   │   ├── supervisor.py          # 调度Agent（主控节点）
│   │   │   ├── state.py               # 共享状态定义
│   │   │   ├── profile_agent.py       # 画像Agent
│   │   │   ├── resource_agent.py      # 资源生成Agent
│   │   │   ├── question_agent.py      # 出题Agent
│   │   │   ├── path_agent.py          # 路径规划Agent
│   │   │   └── evaluation_agent.py    # 评估反馈Agent
│   │   │
│   │   ├── models/                    # SQLAlchemy ORM模型
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── profile.py
│   │   │   ├── resource.py
│   │   │   └── assessment.py
│   │   │
│   │   ├── schemas/                   # Pydantic请求/响应模型
│   │   │   ├── __init__.py
│   │   │   ├── chat.py
│   │   │   ├── profile.py
│   │   │   └── resource.py
│   │   │
│   │   ├── services/                  # 业务逻辑层
│   │   │   ├── __init__.py
│   │   │   ├── spark_client.py        # 讯飞星火API封装
│   │   │   ├── embedding_service.py   # Embedding服务（BGE）
│   │   │   ├── rag_service.py         # RAG检索+防幻觉校验
│   │   │   └── resource_service.py    # 资源管理服务
│   │   │
│   │   ├── core/                      # 核心基础设施
│   │   │   ├── __init__.py
│   │   │   ├── database.py            # MySQL连接
│   │   │   ├── redis_client.py        # Redis连接
│   │   │   ├── chroma_client.py       # ChromaDB连接
│   │   │   ├── minio_client.py        # MinIO连接
│   │   │   └── security.py            # JWT+密码哈希
│   │   │
│   │   └── utils/                     # 工具函数
│   │       ├── __init__.py
│   │       └── markdown_utils.py      # Markdown→思维导图转换
│   │
│   └── tests/                         # 后端测试
│       ├── conftest.py
│       ├── test_agents/
│       └── test_api/
│
├── frontend/                          # Vue3 前端
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── router/
│   │   │   └── index.ts              # 路由配置
│   │   ├── stores/                   # Pinia状态管理
│   │   │   ├── user.ts               # 用户状态
│   │   │   ├── chat.ts               # 对话状态
│   │   │   └── learning.ts          # 学习状态
│   │   ├── api/                      # 后端API调用封装
│   │   │   ├── index.ts              # axios实例
│   │   │   ├── chat.ts               # SSE流式对话
│   │   │   ├── auth.ts
│   │   │   └── resource.ts
│   │   ├── views/                    # 页面组件
│   │   │   ├── Login.vue
│   │   │   ├── Dashboard.vue         # 学习仪表盘（首页）
│   │   │   ├── ChatView.vue          # Agent对话界面（核心）
│   │   │   ├── ProfileView.vue       # 学习画像展示
│   │   │   ├── ResourceView.vue      # 资源库浏览
│   │   │   ├── AssessmentView.vue    # 评估报告
│   │   │   └── LearningPathView.vue  # 学习路径可视化
│   │   ├── components/               # 可复用组件
│   │   │   ├── chat/
│   │   │   │   ├── ChatMessage.vue   # 消息气泡（支持Markdown）
│   │   │   │   ├── ChatInput.vue     # 输入框（支持附件）
│   │   │   │   └── StreamingText.vue # SSE流式文字渲染
│   │   │   ├── resource/
│   │   │   │   ├── ResourceCard.vue  # 资源卡片
│   │   │   │   └── MindMap.vue       # 思维导图组件（markmap）
│   │   │   ├── assessment/
│   │   │   │   ├── RadarChart.vue    # 6维雷达图
│   │   │   │   └── ScoreBoard.vue    # 成绩面板
│   │   │   └── common/
│   │   │       └── AppLayout.vue     # 通用布局（侧边栏+顶栏）
│   │   └── styles/
│   │       └── global.css
│   └── public/
│       └── favicon.ico
│
└── docs/                              # 比赛文档产出
    ├── 需求分析文档.md
    ├── 技术设计文档.md
    ├── 测试报告.md
    └── 演示脚本.md
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

### ChromaDB 集合设计

| 集合名 | 存储内容 | Embedding模型 | 用途 |
|------|------|------|------|
| `knowledge_base` | 教材/课件文本切片 | BGE-large-zh | RAG知识检索 |
| `resource_embeddings` | 生成的学习资源摘要 | BGE-large-zh | 资源语义搜索 |
| `question_bank` | 题库题目+答案+解析 | BGE-large-zh | 相似题检索 |
| `error_patterns` | 常见错误模式向量 | BGE-large-zh | 错误模式聚类 |

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

### State 定义（共享状态）

```python
from typing import TypedDict, List, Optional, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    # 消息历史（自动追加）
    messages: Annotated[List[BaseMessage], add_messages]

    # 当前激活的Agent
    current_agent: str              # "supervisor" | "profile" | "resource" | ...

    # 路由决策
    next_agent: Optional[str]       # Supervisor决定下一个调用誰

    # 用户画像（从MySQL加载，Agent更新）
    user_profile: Optional[dict]

    # 当前上下文
    context: dict                   # {"topic": "Python基础", "task": "生成资源", ...}

    # 各Agent的输出缓存（避免重复生成）
    agent_outputs: dict             # {"profile_agent": {...}, "resource_agent": {...}}

    # 流式输出缓冲区
    stream_buffer: str              # SSE推送给前端的增量文本

    # 用户ID（从JWT解析）
    user_id: int
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
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
EMBEDDING_DEVICE=cpu   # 或 cuda（有GPU的话）
```

---

## 七、Docker Compose（一键启动基础设施）

```yaml
# docker-compose.yml
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
      - "3306:3306"
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
    image: chromadb/chroma:latest
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

## 八、API路由设计

| 方法 | 路径 | 说明 | 流式 |
|------|------|------|:--:|
| POST | `/api/auth/register` | 注册 | |
| POST | `/api/auth/login` | 登录（返回JWT） | |
| GET | `/api/auth/me` | 获取当前用户信息 | |
| POST | `/api/chat/send` | 发送消息（核心接口） | ✅ SSE |
| GET | `/api/chat/history?conversation_id=` | 获取对话历史 | |
| GET | `/api/profile/me` | 获取学习画像 | |
| PUT | `/api/profile/me` | 更新学习画像 | |
| GET | `/api/resources?type=&page=&size=` | 获取资源列表 | |
| GET | `/api/resources/{id}` | 获取资源详情 | |
| POST | `/api/resources/generate` | 手动触发资源生成 | |
| POST | `/api/assessment/start` | 开始一次评估测试 | |
| POST | `/api/assessment/submit` | 提交答题结果 | |
| GET | `/api/assessment/report/{id}` | 获取评估报告 | |
| GET | `/api/path/current` | 获取当前学习路径 | |
| POST | `/api/path/plan` | 生成/更新学习路径 | |

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

## 九、前端路由与组件树

### 路由设计

```
/login                    → Login.vue           （登录注册页）
/dashboard                → Dashboard.vue       （学习仪表盘首页）
/chat                     → ChatView.vue        （Agent对话 - 核心页面）
/chat/:conversation_id    → ChatView.vue        （历史对话）
/profile                  → ProfileView.vue     （学习画像）
/resources                → ResourceView.vue    （资源库）
/resources/:id            → ResourceView.vue    （资源详情）
/assessment               → AssessmentView.vue  （评估报告）
/learning-path            → LearningPathView.vue（学习路径）
```

### 核心组件：ChatView.vue（对话界面）

```
ChatView.vue
├── 左侧：对话列表（历史会话）
│   └── ConversationList.vue
├── 中间：对话区
│   ├── MessageList.vue         （消息列表，自动滚动到底部）
│   │   ├── ChatMessage.vue     （单条消息，支持Markdown渲染）
│   │   │   ├── 文字内容（marked渲染）
│   │   │   ├── 思维导图（markmap组件）
│   │   │   ├── 代码块（highlight.js）
│   │   │   └── 资源卡片（ResourceCardInline.vue）
│   │   └── StreamingText.vue   （SSE流式打字效果）
│   └── ChatInput.vue           （底部输入框，支持Shift+Enter换行）
└── 右侧：上下文面板（可选折叠）
    ├── 当前画像摘要
    ├── 关联资源推荐
    └── 学习进度条
```

### Pinia Store 设计

```typescript
// stores/chat.ts
interface ChatState {
  conversations: Conversation[]
  currentConversationId: number | null
  messages: Message[]
  isStreaming: boolean          // 是否正在接收SSE
  currentAgent: string          // 当前活跃的Agent
  agentOutputs: Record<string, any>  // 各Agent输出
}

// stores/user.ts
interface UserState {
  token: string | null
  userInfo: User | null
  profile: LearningProfile | null
}
```

---

## 十、实现路线图（按52天规划执行）

### 第一阶段：调研验证（5.9 - 5.15）— 当前所在
- [ ] 5.9-10: 注册讯飞星火，跑通Hello World API调用
- [ ] 5.10-11: 研读参考项目 `zzzlip/langgraph-AI-interview-agent`
- [ ] 5.11-12: LangGraph Quick Start + Supervisor模式Tutorial
- [ ] 5.13: ChromaDB Quick Start + Embedding检索
- [ ] 5.14: 搭项目脚手架（Vue3 + FastAPI + Docker Compose）
- [ ] 5.15: 里程碑1 - 技术验证通过

### 第二阶段：MVP核心闭环（5.16 - 5.31）
- [ ] 5.16-18: 画像Agent（对话采集 + 结构化存储 + 6维画像）
- [ ] 5.19-21: 资源Agent（文档 + 思维导图，先做2种）
- [ ] 5.22-24: 出题Agent（自适应出题 + 答案解析）
- [ ] 5.25-27: 路径Agent（知识图谱 + DAG路径规划）
- [ ] 5.28-29: 评估Agent（答题评估 + 雷达图）
- [ ] 5.30-31: 调度Agent（串联5个Agent + 端到端调试）
- [ ] 5.31: 里程碑2 - MVP闭环可演示

### 第三阶段：前端 + 体验（6.1 - 6.10）
- [ ] 6.1-3: Vue3页面：Dashboard + ChatView
- [ ] 6.4-5: SSE流式输出 + 资源卡片展示
- [ ] 6.5-6: 学习路径DAG可视化
- [ ] 6.7-8: 多模态答疑界面
- [ ] 6.9-10: 全流程联调
- [ ] 6.10: 里程碑3 - 前端体验闭环

### 第四阶段：加分项（6.11 - 6.20）
- [ ] 6.11-12: RAG知识库（教材入库 + 防幻觉校验）
- [ ] 6.13-14: 多模态资源（TTS + 动画）
- [ ] 6.15-16: 评估系统升级（多维雷达 + 策略建议）
- [ ] 6.17-18: 性能优化 + Docker化
- [ ] 6.19-20: 安全加固 + 日志

### 第五阶段：文档演示（6.21 - 6.29）
- [ ] 6.21-23: 需求分析文档
- [ ] 6.24-25: 技术设计文档
- [ ] 6.25-26: 测试报告
- [ ] 6.27-28: 演示视频录制
- [ ] 6.28-29: PPT制作
- [ ] 6.29: 最终审查

### 提交（6.30）
- [ ] 08:00 最后检查
- [ ] 10:00 上传作品
- [ ] 14:00 确认提交成功
- [ ] 15:00 截止

---

## 十一、给下一个Claude会话的启动指令

> 如果这是全新的Claude Code会话，请按以下步骤快速恢复：

```
1. 阅读本文件（CLAUDE.md）- Claude会自动加载
2. 运行 git status 了解当前代码状态
3. 检查 Docker 是否运行：docker ps
4. 检查配置文件：cat .env （如果存在）
5. 告诉我当前进度，我会告诉你下一步做什么
6. 如果项目脚手架还没搭，从"第一阶段 5.14 搭项目脚手架"开始
```

**当前进度追踪方式：**
- 每完成一个任务，我会在对应的 `- [ ]` 前打勾改为 `- [x]`
- 下一个会话的Claude读取此文件就能知道做到哪里了

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
| BGE模型 | https://huggingface.co/BAAI/bge-large-zh-v1.5 |
| markmap（思维导图） | https://markmap.js.org/ |
| Vue Flow（DAG图） | https://vueflow.dev/ |
| Docker Desktop下载 | https://www.docker.com/products/docker-desktop/ |

---

## 附录A：快速启动脚本

```bash
# ===== 首次搭建（Windows PowerShell）=====

# 1. 克隆参考项目研读
git clone https://github.com/zzzlip/langgraph-AI-interview-agent.git /tmp/reference-project

# 2. 创建项目目录
mkdir a3-learning-system
cd a3-learning-system

# 3. 启动基础设施
docker-compose up -d

# 4. 后端
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt

# 5. 初始化数据库
cd backend
alembic upgrade head

# 6. 前端
cd ../frontend
npm install
npm run dev

# 7. 后端启动
cd ../backend
uvicorn app.main:app --reload --port 8000

# ===== 验证服务 =====
# 后端API文档: http://localhost:8000/docs
# 前端页面: http://localhost:5173
# MinIO控制台: http://localhost:9001
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
A: 检查3个值：APP_ID、API_KEY、API_SECRET。注意API_SECRET不同于API_KEY。

**Q: ChromaDB连接失败？**
A: 确保Docker的chromadb容器在运行：`docker-compose up -d chromadb`

**Q: BGE模型下载慢？**
A: 设置HuggingFace镜像：
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

**Q: LangGraph图不执行？**
A: 检查checkpointer是否正确配置，每次调用需要传thread_id。

---

> 📌 **这是项目的唯一真相源文件。任何技术决策、架构设计、配置信息都记录在此。**
> 每次完成阶段性任务后，更新第一部分的"项目当前状态"和第十部分的任务勾选。
