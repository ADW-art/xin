import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.{test,spec}.{ts,js}'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{vue,ts}'],
    },
  },
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),   // 配置 @ 指向 src 目录，与 tsconfig.json 的 paths 保持一致
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        // 修复 ECONNRESET：SSE 长连接 + LangGraph 编排可能耗时数分钟
        // 关闭 Vite 默认代理超时，避免被中间件重置连接
        proxyTimeout: 0,           // 0 = 禁用超时
        timeout: 0,                // 0 = 禁用 socket 超时
        ws: true,                  // 支持 SSE/WS
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
