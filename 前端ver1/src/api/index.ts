/*
axios HTTP 客户端实例

作用：
  创建统一的 HTTP 请求客户端，配置基础路径、超时时间
  通过拦截器实现全局的 JWT 自动附加和 401 自动跳转

关联文件：
  api/chat.ts  ← SSE 流式请求用 fetch（不是 axios），但配置参考本文件
  views/       ← 其他页面通过本实例发送 REST 请求

使用方式：
  import api from '@/api'
  api.get('/profile/me')        -> GET /api/profile/me
  api.put('/profile/me', data)  -> PUT /api/profile/me
*/
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      // 如果已经在登录页，不做跳转（保留错误信息给 Login.vue 展示）
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
