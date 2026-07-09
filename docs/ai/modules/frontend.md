# 前端模块 — Vue 3
## 位置
a3-learning-system/frontend/
## 技术栈
- Vue 3 + TypeScript + Vite + Element Plus + Pinia + Vue Router
- ECharts 图表 + Mermaid 流程图 + axios HTTP
## 构建命令
- npm run dev — 开发服务器（端口 5173）
- npm run build — 生产构建（vue-tsc 类型检查 + vite build）
- npm run test — vitest 跑测试
## 代理配置
- vite.config.ts 中 /api → http://localhost:8001
- proxyTimeout=0, timeout=0（不超时，LLM 可能耗时久）
- SSE/WebSocket 代理已开启
