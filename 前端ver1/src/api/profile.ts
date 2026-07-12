/*
画像 API（profile）

作用：
  封装学习画像的获取和更新请求
  后端路由：GET /api/profile/me 和 PUT /api/profile/me

关联文件：
  stores/user.ts  ← 调用本文件的函数获取和更新画像
  api/index.ts    ← 底层 axios 实例

使用方式：
  import { getProfile, updateProfile } from '@/api/profile'
*/

import api from './index'

// 6 维学习画像数据结构（与后端 ProfileResponse schema 对齐）
export interface LearningProfile {
  user_id: number
  knowledge_base: Record<string, number> | null       // 知识点掌握度 {"Python": 60, "数学": 70}
  cognitive_style: string | null                       // visual / auditory / kinesthetic / reading
  learning_goal: string | null                         // exam / skill / career / interest
  weekly_hours: number | null                          // 每周可投入学习时间
  error_patterns: Array<{ type: string; concepts: string[] }> | null  // 易错模式
  preferred_resource_type: string | null               // video / text / code / interactive
  dimension_scores: Record<string, number> | null      // 各维度量化分数
}

// 画像更新的请求体（所有字段可选，只更新传入的字段）
export interface ProfileUpdateData {
  knowledge_base?: Record<string, number>
  cognitive_style?: string
  learning_goal?: string
  weekly_hours?: number
  error_patterns?: Array<{ type: string; concepts: string[] }>
  preferred_resource_type?: string
  dimension_scores?: Record<string, number>
}

// 获取当前用户的学习画像（无画像时后端自动创建默认画像）
export async function getProfile(): Promise<LearningProfile> {
  const response = await api.get<LearningProfile>('/profile/me')
  return response.data
}

// 更新学习画像（只传需要修改的字段）
export async function updateProfile(data: ProfileUpdateData): Promise<LearningProfile> {
  const response = await api.put<LearningProfile>('/profile/me', data)
  return response.data
}
