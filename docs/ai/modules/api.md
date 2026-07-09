# API 路由模块
## 位置
a3-learning-system/backend/app/api/
## 路由列表
### auth.py — 认证
- POST /api/auth/register — 注册
- POST /api/auth/login — 登录
- GET /api/auth/me — 获取当前用户
### chat.py — 对话
- POST /api/chat — 对话交互（核心入口，走 Supervisor 调度）
### profile.py — 用户画像
- GET /api/profile — 获取画像
- PUT /api/profile — 更新画像
### assessment.py — 学习评估
- GET /api/assessment — 获取评估报告
### learning_path.py — 学习路径
- GET /api/learning-path — 获取路径规划
### resources.py — 学习资源
- GET /api/resources — 获取资源列表
### conversation.py — 会话管理
- GET /api/conversations — 会话列表
- GET /api/conversations/{id} — 会话详情
### bkt.py — 知识追踪
- GET /api/bkt/status — BKT 状态
- POST /api/bkt/update — 更新 BKT
### agent_trace.py — Agent 追踪
- GET /api/agent-trace — Agent 调用链追踪
### review.py — 复习管理
- GET /api/review — 复习计划
- POST /api/review — 创建复习
### admin.py + tts.py + video.py + recommend.py — 管理/语音/视频/推荐
