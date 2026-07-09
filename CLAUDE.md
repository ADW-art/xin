# A3 学习系统 — AI 治理规则 (Governance Engineering v1.3)

## 项目概述
A3 个性化学习系统项目 — 后端 FastAPI+LangGraph 多智能体，前端 Vue 3+Element Plus。

## 项目铁律（11条，违反即不合格输出）

### 1. 赛道要求
**严格遵守软件杯 A3 赛道官网要求。** 任何与赛道要求冲突的功能、设计、技术选型均禁止。

### 2. 业内对标
**模仿业内优秀同类项目，不要自己编造代码。** 改代码前先调研同类成熟实现，参考其模式和风格。

### 3. 禁止 Emoji
**全局不能使用 Emoji。** 包括 UI、注释、日志、提交信息、文档。

### 4. 视觉风格
**蓝白配色为主，CSS 样式全局统一。** 警告用黄色/红色/蓝色，参考教育类网页设计。

### 5. 质量对标
**完全对标省一，不得降级代码。** 功能完整性、代码质量、测试覆盖、文档完备度均以省一标准衡量。

### 6. 方案确认
**发现任何不确定的点，必须敲定方案后再继续。** 不得自行猜测用户意图。

### 7. 先启动后修改
**先保证项目正常启动，再修代码。** 不要在已有 bug 上叠代码。遇到阻塞先修复，再继续开发。

### 8. 首尾检查
**一次工作完成后必须进行首尾检查：**
- 项目是否正常运行
- 修改的代码是否冗余
- 当前功能状态是否更新
- 还有什么工作未完成（报告）
- 临时文件是否清理

### 9. 错误记录
**同一次工作中多次出现的相同错误，必须记录在 docs/ai/errors/ 中，以后不再犯。**

### 10. 工具装载
**有需要的工具和能力，向用户询问装载。** 不得第一考虑降级方案。

### 11. 进度更新
**一次工作完成后必须更新工作进度。** 用 update_plan 或文档记录。

## 核心铁律
AI 作为调度者 — 不直接执行任务。一切工作经过治理流水线。

## 常用命令
- **测试**: `make test` — 跑后端+前端全部测试
- **后端测试**: `cd a3-learning-system/backend && python -m pytest tests/ -v`
- **VCS 状态**: `git status`
- **VCS 差异**: `git diff`

## 流水线
用户输入 → [confirm-agent] 确认需求 → 展示 confirm_result YAML
  → AskUserQuestion "需求理解是否正确？"       [暂停点1]
     ↻ 用户拒绝/修改 → 重新确认 (≤5 次)
  → SIMPLE (score≥70): developer → test → commit
  → STANDARD (<70): explore → [plan-agent] → 方案确认 → developer → [inspector] → [test] → 首尾检查 → commit
  → AUTO-PIPELINE (≥85+NONE+≤20LOC): 跳过暂停点1

## Agent 清单
| Agent | 职责 |
|-------|------|
| confirm-agent | 歧义检测 + 复杂度评分 + 需求重述 |
| explore-agent | 四层渐进代码搜索 |
| plan-agent | 方案规划 + 任务分解 |
| developer-agent | 代码生成 + 自审 + 测试 + ≤3次修复循环 |
| inspector-agent | 独立审查 |
| test-agent | 测试生成与执行 |
| summarize-agent | 知识沉淀 |
| commit-agent | 提交信息生成 |

## 知识管理
- docs/ai/errors/ — 重复错误记录
- docs/ai/modules/ — 模块卡片
- docs/ai/decisions/ — 架构决策
- 每次工作完成后 summarize-agent 更新知识库

## 编码规范
见 .claude/rules/coding-standards.md

## 架构约定
见 .claude/rules/project-map.md
