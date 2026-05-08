# Agent Skills 完整操作使用指南

> 插件：agent-skills@addy-agent-skills（Addy Osmani 出品）
> 安装日期：2026-05-09

---

## 一、安装方法

```bash
# 1. 添加插件市场
claude plugin marketplace add addyosmani/agent-skills

# 2. 如果 SSH 连不上 GitHub，先切 HTTPS
git config --global url."https://github.com/".insteadOf "git@github.com:"

# 3. 安装插件
claude plugin install agent-skills@addy-agent-skills

# 4. 重启 Claude Code（斜杠命令需要重启后才能用）
```

或直接在 Claude Code 对话框输入：

```
/plugin marketplace add addyosmani/agent-skills
/plugin install agent-skills@addy-agent-skills
```

---

## 二、7 个斜杠命令

在对话框直接输入即可：

| 命令 | 用途 | 什么时候用 |
|------|------|-----------|
| `/spec` | 写需求规格文档 | 有新想法、新功能要做 |
| `/plan` | 任务拆分 & 依赖排序 | 规格定了，要知道怎么做 |
| `/build` | 增量实现 + TDD 测试 | 开始写代码 |
| `/test` | 测试驱动开发 / 复现 Bug | 写测试、修 Bug |
| `/code-simplify` | 简化代码，不改变行为 | 代码太乱，要重构 |
| `/review` | 五维代码审查 | 提交前，让 AI 审查 |
| `/ship` | 三审并行 + 上线决策 | 准备合并/发布 |

### 全流程

```
/spec → /plan → /build → /test → /review → /ship
```

---

## 三、各命令详解

### `/spec` — 需求规格

AI 会问你这四个问题：

1. 目标和目标用户
2. 核心功能和验收标准
3. 技术栈偏好和约束
4. 已知边界（做什么、先问再做、绝不做什么）

然后生成 `SPEC.md` 放在项目根目录。

### `/plan` — 任务规划

- 先读 SPEC.md 和代码库
- 画出依赖关系图
- **垂直切分**（一个完整路径一个任务，不是水平分层）
- 每个任务有验收标准 + 验证步骤
- 生成 `tasks/plan.md` 和 `tasks/todo.md`

### `/build` — 增量实现

每个任务的流程：

```
读验收标准 → 加载上下文 → 写失败测试(RED) → 实现(GREEN) → 跑全量测试 → 构建编译 → 提交
```

- 一次只做一个增量
- 超过 100 行还不跑测试就是红旗
- 不碰任务范围外的文件

### `/test` — 测试驱动

- **新功能**：先写测试（应该 FAIL）→ 实现 → 重构
- **修 Bug**（Prove-It 模式）：先写能复现 Bug 的测试 → 确认失败 → 修 → 确认通过
- 浏览器相关的附带调用 Chrome DevTools MCP

### `/code-simplify` — 代码简化

检查项：
- 深层嵌套 → 卫语句或提取辅助函数
- 长函数 → 按职责拆分
- 嵌套三元 → if/else 或 switch
- 泛化命名 → 具名化
- 重复逻辑 → 共享函数
- 死代码 → 确认后删除

每次改动后跑测试，失败就回滚。

### `/review` — 五维代码审查

| 维度 | 检查内容 |
|------|---------|
| 正确性 | 符合规格？边界情况？测试够？ |
| 可读性 | 命名清晰？逻辑直白？结构合理？ |
| 架构 | 遵循已有模式？边界清晰？抽象适度？ |
| 安全性 | 输入验证？密钥安全？权限检查？ |
| 性能 | 无 N+1 查询？无无界操作？ |

输出结构：Critical / Important / Suggestion 三级，标注 `文件:行号`。

### `/ship` — 发布审查（重磅命令）

**Phase A — 三个 Agent 并行审查：**

```
/ship
  ├── code-reviewer    → 五维代码审查
  ├── security-auditor → OWASP + 密钥 + 认证 + CVE
  └── test-engineer    → 测试覆盖率分析
```

**Phase B — 主 Agent 合并报告**，去重、交叉验证。

**Phase C — 决策输出**：
- GO / NO-GO
- 阻断项（必须修）
- 建议修（最好修）
- 已知风险（接受）
- **回滚方案**（必须有）

---

## 四、20 个自动 Skill（自动激活，无需手动调用）

### 定义阶段

| Skill | 触发条件 |
|-------|---------|
| `idea-refine` | 需求模糊、想法需要打磨 |
| `spec-driven-development` | 新项目/功能/改动，需要规格 |

### 规划阶段

| Skill | 触发条件 |
|-------|---------|
| `planning-and-task-breakdown` | 有规格，需要拆分任务 |

### 构建阶段

| Skill | 触发条件 |
|-------|---------|
| `incremental-implementation` | 开始写代码 |
| `frontend-ui-engineering` | UI 相关开发 |
| `api-and-interface-design` | API/接口设计 |
| `context-engineering` | 需要更好的上下文 |
| `source-driven-development` | 需要验证官方文档 |

### 验证阶段

| Skill | 触发条件 |
|-------|---------|
| `test-driven-development` | 写测试/修 Bug |
| `browser-testing-with-devtools` | 浏览器端测试 |
| `debugging-and-error-recovery` | 出问题了要排查 |

### 审查阶段

| Skill | 触发条件 |
|-------|---------|
| `code-review-and-quality` | 审查代码 |
| `code-simplification` | 简化重构 |
| `security-and-hardening` | 安全审查 |
| `performance-optimization` | 性能优化 |

### 上线阶段

| Skill | 触发条件 |
|-------|---------|
| `git-workflow-and-versioning` | 提交/分支操作 |
| `ci-cd-and-automation` | CI/CD 相关 |
| `documentation-and-adrs` | 写文档/架构决策 |
| `shipping-and-launch` | 部署/发布 |
| `deprecation-and-migration` | 废弃/迁移 |

---

## 五、3 个专属 Agent 审查员

这些是 `Agent` 工具可调用的子代理：

| 审查员 | 职责 |
|--------|------|
| `code-reviewer` | 五维代码审查（正确性/可读性/架构/安全/性能） |
| `security-auditor` | OWASP Top 10、密钥处理、认证/授权、依赖 CVE |
| `test-engineer` | 测试覆盖率分析（正常路径/边界/错误/并发） |

---

## 六、六大核心原则（AI 行为准则）

这些原则在所有 Skill 中强制执行：

1. **暴露假设** — 实现前先列出假设，让用户纠错
2. **管理困惑** — 遇到矛盾时停手，提出澄清问题，不要猜
3. **必要的反对** — 发现方案有问题直接指出，不做应声虫
4. **强制简洁** — 能用 100 行解决绝不写 1000 行
5. **范围纪律** — 只碰被要求改的东西，不顺手重构
6. **验证不假设** — 每步必须有证据（测试通过、构建成功、运行数据），"看着对"不算

---

## 七、日常使用建议

### 写新功能（走全流程）

```
/spec   → 产出 SPEC.md
/plan   → 产出 tasks/plan.md + tasks/todo.md
/build  → 逐个任务实现
/test   → 跑测试验证
/review → 代码审查
/ship   → 三审并行 + 发布决策
```

### 修 Bug

直接描述 Bug，AI 自动走 `debugging-and-error-recovery` → `test-driven-development` → `code-review-and-quality`

### 小修改

直接说需求，AI 走 `incremental-implementation` + `code-simplification`

### 推代码前

```
/review   # 让 AI 审查一遍
```

### 重要发布前

```
/ship     # 三个审查员并行审查 + 回滚方案
```

---

## 八、注意事项

- 插件安装后需要**重启 Claude Code**，斜杠命令才会出现
- Skill 是**自动激活**的，你正常对话就行，不需要手动选择
- 任何时候也可以用 `/spec`、`/review` 等命令手动触发
- 不是每个任务都要走完全流程，小修改直接 `/build`，修 Bug 直接描述即可
- `/ship` 的并行审查是重型流程，适合重要改动；2 个文件以内、不到 50 行的小改动可跳过
