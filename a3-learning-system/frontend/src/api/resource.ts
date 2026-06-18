/*
资源 API（resource）

作用：
  封装学习资源的获取请求
  后端路由：GET /api/resources 和 GET /api/resources/{id}

关联文件：
  stores/learning.ts  ← 调用本文件的函数管理资源状态
  api/index.ts        ← 底层 axios 实例

使用方式：
  import { getResources, getResource } from '@/api/resource'
*/

import api from './index'

// 单个资源的数据结构（与后端 ResourceListResponse 对齐）
export interface ResourceItem {
  id: number
  resource_type: 'document' | 'mindmap' | 'question_set' | 'video_script' | 'code_example'
  title: string
  knowledge_points: string[] | null        // 关联知识点
  difficulty_level: number | null          // 1-5 难度等级
  generated_by: string | null              // 生成此资源的 Agent 名称
  created_at: string                       // ISO 日期字符串
}

// 资源详情的结构（包含 content 字段）
export interface ResourceDetail extends ResourceItem {
  content: string | null                   // 资源正文（Markdown / 代码 / 题目等）
  file_url: string | null                  // MinIO 文件地址
  feedback_score: number | null            // 用户评分 1-5
}

// 资源列表查询参数
export interface ResourceQueryParams {
  type?: string       // 资源类型过滤
  page?: number       // 页码，从 1 开始
  size?: number       // 每页条数
}

// 获取资源列表（支持按类型过滤和分页）
export async function getResources(params?: ResourceQueryParams): Promise<ResourceItem[]> {
  const response = await api.get<ResourceItem[]>('/resources', { params })
  return response.data
}

// 获取单个资源的完整详情
export async function getResource(id: number): Promise<ResourceDetail> {
  const response = await api.get<ResourceDetail>(`/resources/${id}`)
  return response.data
}
