# A3 学习系统 — 编码规范

## 铁律
- 全局禁止使用 Emoji（注释、日志、UI、提交信息、文档均不可用）
- 蓝白配色为主，CSS 样式全局统一
- 警告信息用黄色/红色/蓝色，参考教育类网页设计

## 后端 (Python FastAPI)
- 遵循 PEP 8
- API 路由在 app/api/ 下
- 复杂业务逻辑在 app/services/ 下
- Agent 定义在 app/agents/ 下
- 数据库操作通过 SQLAlchemy Session

## 前端 (Vue 3 + TypeScript)
- 使用 Element Plus 组件库
- 蓝白主题色
- 全局 CSS 变量统一管理动效（动画时长、缓动函数一致）
- 状态管理用 Pinia
- 路由用 Vue Router

## 测试规范
- 后端测试用 pytest，放在 tests/
- conftest.py 已 mock 数据库和 LLM
- 新增功能必须有测试覆盖
- bug 修复必须有 regression test

## 命名约定
- 后端: snake_case
- API 路由: /api/{resource}/
- 前端: camelCase (JS/TS), PascalCase (组件)
- Agent: {role}_agent.py
