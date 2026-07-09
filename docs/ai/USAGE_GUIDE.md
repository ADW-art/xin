# A3 学习系统 - 治理工程使用指南

## 双工具架构说明

本项目同时使用 Codex 和 Claude Code 两个 AI 工具。
治理文件分别在各自工具加载时生效：

### 工具对照表

| 你的操作 | 哪个工具 | 生效的治理文件 |
|---------|---------|--------------|
| 在 Codex 中聊天 | Codex (我) | CLAUDE.md + .codex/hooks.json |
| 启动 Claude Code | Claude Code | CLAUDE.md + .claude/agents/ + .claude/rules/ |
| 查项目知识 | 两者 | docs/ai/MODULE_INDEX.md |

### 当使用 Codex（我）时

你说目标，我（Codex）自动走治理流水线：

```
闸门1: 我重述需求，列出涉及文件 — 你确认
闸门2（复杂任务）: 我出方案 — 你审批
执行: 我改代码 + 跑测试
闸门3: 我展示改动 + 测试结果 — 你验收
```

### 当使用 Claude Code 时

Claude Code 读取 `.claude/agents/` 下的 11 个 Agent 定义，
使用 Fork 机制在独立上下文中执行子任务。
CLAUDE.md 中的流水线规则同样适用。

### 知识库共享

两个工具共享 `docs/ai/` 知识库：
- MODULE_INDEX.md — 模块索引
- modules/ — 模块卡片
- decisions/ — 架构决策
- USAGE_GUIDE.md — 使用指南

无论用哪个工具做的修改，知识都沉淀到同一位置。
