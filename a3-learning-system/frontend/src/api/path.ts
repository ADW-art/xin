/*
学习路径 API（path）

作用：
  封装学习路径的获取请求
  后端路由：GET /api/path/current

关联文件：
  stores/learning.ts  ← 调用本文件的函数管理路径状态
  api/index.ts        ← 底层 axios 实例

使用方式：
  import { getCurrentPath } from '@/api/path'
*/

import api from './index'

// 学习路径的数据结构（与后端 PathResponse 对齐）
export interface LearningPath {
  id: number
  user_id: number
  path_data: {                              // DAG 结构的路径数据
    nodes: Array<{
      id: number
      label: string                         // 知识点名称
      description?: string
      estimated_hours?: number              // 建议学习时长
      difficulty?: number                   // 难度等级
    }>
    edges: Array<{
      source: number                        // 前置知识点 ID
      target: number                        // 后继知识点 ID
    }>
  } | null
  current_node: number | null               // 当前所在节点序号
  status: 'active' | 'completed' | 'paused'
  started_at: string | null
  completed_at: string | null
  created_at: string
}

// 获取当前用户活跃的学习路径
export async function getCurrentPath(): Promise<LearningPath | null> {
  const response = await api.get<LearningPath | null>('/path/current')
  return response.data
}
