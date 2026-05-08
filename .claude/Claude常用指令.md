# Claude Code 常用指令

## 基础命令

### 启动 Claude Code
```bash
# 基础启动
claude

# 在指定目录启动
claude /path/to/project

# 在新窗口启动（Windows）
claude --new-window
```

### 退出 Claude Code
```bash
# 退出当前会话
exit

# 或使用快捷键
Ctrl+C
```

## 权限管理命令

### 跳过权限检查（谨慎使用）
```bash
# 完全跳过所有权限检查（仅建议在无互联网访问的沙盒中使用）
claude --dangerously-skip-permissions

# 允许跳过权限作为选项（不默认启用）
claude --allow-dangerously-skip-permissions

# 设置权限模式
claude --permission-mode bypassPermissions  # 跳过权限
claude --permission-mode dontAsk           # 不询问，自动批准
claude --permission-mode plan               # 需要计划批准
claude --permission-mode acceptEdits       # 自动批准编辑
claude --permission-mode auto              # 自动模式
```

### 权限模式说明
- `default`: 默认模式，会询问关键操作
- `acceptEdits`: 自动批准编辑操作
- `auto`: 自动批准大多数操作
- `bypassPermissions`: 完全绕过权限检查
- `dontAsk`: 不询问，自动批准
- `plan`: 需要计划批准（适合重要变更）

## 项目和文件操作

### 初始化项目
```bash
# 初始化 CLAUDE.md 文件
/init

# 初始化新的 Claude Code 项目配置
claude --init
```

### 文件搜索和操作
```bash
# 搜索文件
/cl <filename>           # 搜索文件名
/cs <content>           # 搜索文件内容
/cg <pattern>          # 使用 glob 模式搜索文件

# 文件操作
/read <file>            # 读取文件
/edit <file>            # 编辑文件
/write <file>           # 写入新文件
```

### Git 操作
```bash
# 查看 Git 状态
/git status

# 提交更改
/commit "提交信息"

# 创建 PR
/pr create              # 创建新的 pull request
/pr view <number>       # 查看 PR
/pr comment <number>    # 评论 PR

# 分支操作
/branch new <name>      # 创建新分支
/branch switch <name>   # 切换分支
```

## 代码分析和审查

### 代码审查
```bash
# 审查当前分支的更改
/review

# 安全审查
/security-review

# 简化代码
/simplify

# 分析代码质量
/analyze-code
```

### 调试和测试
```bash
# 运行测试
/test

# 调试模式
/debug

# 性能分析
/profile
```

## 高级功能

### 任务管理
```bash
# 查看任务列表
/tasks

# 创建新任务
/task "任务描述"

# 更新任务状态
/task <id> status done
/task <id> status in_progress
```

### 定时任务
```bash
# 设置定时任务（每5分钟运行一次）
/loop 5m /command

# 设置一次性提醒
/remind 10m "检查构建状态"

# 自定义定时任务
/loop "*/5 * * * *" "执行健康检查"
```

### 技能和插件
```bash
# 查看可用技能
/skills

# 使用技能
/<skill-name>

# 添加技能
/add-skill <plugin>:<skill>
```

### 配置管理
```bash
# 查看配置
/config

# 编辑配置
/config edit

# 设置环境变量
/set VAR_NAME=value

# 添加权限
/allow <command>
```

## 快捷键

### 基础操作
- `Ctrl+Enter`: 提交输入
- `Ctrl+K`: 清除当前输入
- `Ctrl+L`: 清除屏幕
- `Ctrl+C`: 退出当前操作
- `Ctrl+Z`: 暂停当前任务

### 导航
- `Ctrl+P`: 打开文件选择器
- `Ctrl+O`: 打开最近文件
- `Ctrl+B`: 切换侧边栏

### 编辑
- `Ctrl+S`: 保存文件
- `Ctrl+Z`: 撤销操作
- `Ctrl+Y`: 重做操作

## 实用技巧

### 1. 使用上下文记忆
Claude Code 会记住之前的对话上下文，可以：
- 引用之前的代码片段
- 继续未完成的任务
- 记住用户的偏好设置

### 2. 批量操作
```bash
# 同时执行多个命令
! git status && npm install && npm test

# 在后台运行任务
/run-in-background long-running-command
```

### 3. 获取帮助
```bash
# 查看帮助
/help

# 查看特定命令的帮助
/help <command>

# 查看键盘快捷键
/keybindings
```

### 4. 自定义配置
```bash
# 编辑设置
/settings edit

# 添加自定义钩子
/add-hook "before_command" "echo 'Starting command'"

# 设置别名
/alias ll "ls -la"
```

## 最佳实践

1. **安全使用权限跳过**
   - 仅在可信环境中使用 `--dangerously-skip-permissions`
   - 避免在有网络访问的环境中完全跳过权限

2. **善用任务管理**
   - 将大任务分解为小任务
   - 使用任务状态跟踪进度
   - 定期查看任务列表

3. **版本控制集成**
   - 重要更改前先提交
   - 使用分支进行实验性工作
   - 定期同步远程分支

4. **性能优化**
   - 使用 `/loop` 进行定期检查
   - 避免不必要的文件搜索
   - 使用缓存功能

## 常见问题

### Q: 如何清除 Claude Code 的缓存？
A: 删除用户配置目录（通常是 `~/.claude/`）

### Q: 如何恢复默认设置？
A: 删除 `settings.json` 或运行 `claude --reset-settings`

### Q: 如何更新 Claude Code？
A: 使用 `npm update -g @anthropic-ai/claude-code`

### Q: 如何导出对话历史？
A: 使用 `/export` 命令或手动复制对话记录