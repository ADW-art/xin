# 架构规则 — Fork 决策矩阵 + 流水线

## 三级任务分类

根据 confirm-agent 输出的 complexity_score 决定:

| 级别 | 分数 | 流水线 | 闸门 |
|------|------|--------|------|
| SIMPLE | >=70 | confirm → developer → test → commit | 跳过闸门2 |
| STANDARD | 30-69 | confirm → explore → plan → developer → test → summarize → commit | 全闸门 |
| COMPLEX | <30 | confirm → explore → plan → developer → inspector → test → summarize → commit | 全闸门 + inspector |

## Fork 决策矩阵

| 场景 | 需要 explore? | 需要 plan? | 需要 inspector? |
|------|:---:|:---:|:---:|
| 单文件 ≤20 LOC 纯改文字/配置 | N | N | N |
| 单文件 ≤20 LOC 逻辑变更 | Y | N | N |
| 多文件改动 | Y | Y | Y |
| 新增 API 端点 | Y | Y | Y |
| 改数据库模型 | Y | Y | Y |
| 新增 Agent | Y | Y | Y |
| Bug 修复 | Y | Y | 仅回归测试 |
| 重构 | Y | Y | Y |

## 暂停点规则

| 暂停点 | 位置 | 跳过条件 |
|--------|------|----------|
| 闸门1: 需求确认 | confirm-agent 输出后 | 永不跳过 |
| 闸门2: 方案审批 | plan-agent 输出后 | SIMPLE 任务跳过 |
| 闸门3: 改后审查 | test-agent 输出后 | 永不跳过 |

## 容错规则
- developer-agent 修复循环：最多 3 轮，超过则回退到 plan-agent
- 用户可随时打回任何阶段
- 被打回后最多重试 3 次，超过则放弃当前任务
