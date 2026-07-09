# A3 Learning System — 完整 API 接入方案

> 共 48 个 API 端点 · 基础地址: http://localhost:8001

---

## 一、认证方式

JWT Bearer Token。注册/登录后返回 token，后续请求在 Header 中传入:

```
Authorization: Bearer <token>
```

### 注册
POST /api/auth/register
Content-Type: application/json
{"username": "test", "password": "test123", "nickname": "测试"}

### 登录
POST /api/auth/login
{"username": "test", "password": "test123"}
→ 返回 {"token": "eyJ...", "user": {...}}

### 获取当前用户
GET /api/auth/me
→ 返回当前用户信息和画像状态

---

## 二、核心功能 API

### 2.1 对话式学习
POST /api/chat/send
Content-Type: application/json
{"content": "我想学Python", "images": [...]}
→ SSE 流式响应 (event: progress / data: {...} / event: message)

注意: 使用 SSE 格式，需用 EventSource 或 fetch streaming 读取。

### 2.2 画像管理
GET /api/profile/me  — 获取当前画像（8维度）
PUT /api/profile/me  — 更新画像字段

### 2.3 资源管理
GET /api/resources — 资源列表
GET /api/resources/{id} — 资源详情
DELETE /api/resources/{id} — 删除
POST /api/resources/{id}/feedback — 提交反馈

### 2.4 学习评估
POST /api/assessment/submit — 提交评估
GET /api/assessment/reports — 评估报告列表
GET /api/assessment/reports/{id} — 单份报告详情
GET /api/assessment/records — 评估记录

### 2.5 BKT 知识追踪
POST /api/bkt/answer — 单题提交
POST /api/bkt/answers — 批量提交
GET /api/bkt/status — BKT 状态总览
POST /api/bkt/em-fit — 触发 EM 拟合

### 2.6 学习路径
GET /api/path/current — 当前路径
GET /api/path/graph — 知识图谱 DAG
GET /api/path/graph/{domain_id} — 指定领域图谱
POST /api/path/replan — 触发路径重规划
GET /api/path/node-resources — 节点关联资源

### 2.7 间隔复习
GET /api/review/due — 到期复习列表
GET /api/review/stats — 复习统计

---

## 三、新功能 API

### 3.1 主动推送推荐 (新增)
GET /api/push/recommendations
Authorization: Bearer <token>
→ 返回:
{
  "weak": ["概念A", "概念B"],     # BKT 薄弱知识点
  "next": ["概念C", "概念D"],     # KG 下一可学知识点
  "resources": [{"id":1, "title":"...", "rtype":"document", "topic":"..."}],
  "mastered": 5,                  # 已掌握数
  "total": 20                     # 总知识点数
}

用途: Dashboard「今日推荐」数据源

### 3.2 TTS 语音合成
POST /api/tts/synthesize
Content-Type: application/json
{"text": "要合成的文本"}
→ 返回 base64 编码的 WAV 音频数据

### 3.3 Agent 追踪
GET /api/agent-trace/manifest — Agent 注册清单
GET /api/agent-trace/latest — 最新 Agent 调用记录

---

## 四、视频生成管线 (T3)

### 4.1 工作流程

resource_agent 产出 video_script
  → video_service.py parse_script() 拆分为 timed_slides[]
  → video_service.py _render() PIL 渲染幻灯片(base64 PNG)
  → video_service.py _tts() TTS 合成音频(base64 WAV)
  → video_service.py gen() 组合为完整 presentation dict

### 4.2 技术栈

静态幻灯片渲染:  PIL 绘制 1280x720 PNG
音频合成:        讯飞星火 TTS API (已有)
音画同步:        SlidePlayer.vue audio.play() + slide 切换
导出视频:        浏览器 MediaRecorder API → .webm 下载

需要补充的后端 API:
POST /api/tts/generate-video
{"script_text": "..."}
→ 返回 {"slides": [...], "audio": [...], "total_dur": 120, "cnt": 5}

---

## 五、数字人集成方案 (可选)

### 5.1 讯飞数字人 API 接入

官网: https://www.xfyun.cn/service/digital-human
文档: https://www.xfyun.cn/doc/digitalMan/digitalHuman/API.html

接入流程:
1. 登录讯飞开放平台 → 控制台 → 创建数字人应用
2. 获取 APP_ID / API_KEY / API_SECRET
3. 在 .env 中添加:
   XF_DIGITAL_APP_ID=xxx
   XF_DIGITAL_API_KEY=xxx
   XF_DIGITAL_API_SECRET=xxx

4. 调用数字人口型驱动 API:
   POST https://api.xf-yun.com/v1/private/digital_human
   {
     "header": {"app_id": "xxx"},
     "parameter": {"digital": {"driver": "audio", "image": "teacher_female"}},
     "payload": {"audio": {"encoding": "mp3", "audio": "<base64_音频数据>"}}
   }

5. 返回的视频流与 slide 时间轴同步即可

### 5.2 与本项目集成方案

在 video_service.py 中新增数字人模式:

```python
def gen_with_digital_human(script_text):
    presentation = gen(script_text)  # 先走标准管线
    # 将音频发送到讯飞数字人 API
    for audio_seg in presentation["audio"]:
        audio_b64 = audio_seg["b64"]
        digital_video = call_xf_digital_human(audio_b64)
        audio_seg["digital_video"] = digital_video
    return presentation
```

### 5.3 注意事项

- 数字人 API 需要企业认证，个人账户可能受限
- 每次调用约 0.5-2 元人民币
- 200字文本约生成 10-15 秒视频
- 建议用于开场介绍和关键概念讲解，不宜全篇使用

---

## 六、调试与测试

### API 调试入口
http://localhost:8001/docs — Swagger UI
http://localhost:8001/redoc — ReDoc

### 快速测试
# 健康检查
curl http://localhost:8001/api/health

# 注册
curl -X POST http://localhost:8001/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123","nickname":"测试"}'

# 登录
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}'

# 推荐 (需替换 TOKEN)
curl http://localhost:8001/api/push/recommendations \
  -H "Authorization: Bearer <TOKEN>"

---

## 七、外部依赖清单

| 依赖 | 用途 | 是否已有 |
|:-----|:-----|:--------:|
| 讯飞星火 Spark API | LLM 对话 + 意图分类 | ✅ .env 已配 |
| 讯飞 TTS API | 语音合成 | ✅ .env 已配 |
| MySQL 8.0 | 数据持久化 | ✅ Docker |
| Redis 7 | 限流 + 缓存 | ✅ Docker |
| MinIO | 对象存储(资源文件) | ✅ Docker |
| ChromaDB | 向量数据库(RAG) | ✅ Docker |
| BGE Embeddings | 文本向量化 | ✅ venv 已装 |
| 讯飞数字人 API | 虚拟教师形象 | ❌ 需额外申请 |
| ffmpeg | mp4 导出 | ❌ 需安装 |

