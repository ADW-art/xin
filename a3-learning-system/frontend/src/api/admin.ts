/*
Admin API 模块

作用：
  封装管理后台相关的后端接口调用 (RAG 管理, 文件上传, 统计)
  替代视图中分散的 api.get('/admin/...') 调用

关联文件：
  views/RagCenter.vue, Dashboard.vue
*/
import api from './index'

export interface AdminStats {
  document_count: number
  vector_count: number
  collection_names: string[]
}

export function getAdminStats() {
  return api.get<AdminStats>('/admin/stats')
}

export function uploadFile(file: File) {
  const form = new FormData()
  form.append('file', file)
  return api.post('/admin/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export interface RagTraceItem {
  stage: string
  candidates: number
  top_k: number
  latency_ms: number
}

export function getRagTrace(query: string) {
  return api.get<{ trace: RagTraceItem[] }>('/admin/rag-trace', {
    params: { query },
  })
}

export function getRagStatus() {
  return api.get('/admin/rag-status')
}
