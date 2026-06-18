/*
评估 API（assessment）

作用：
  封装评估报告和答题记录的相关请求
  后端路由：
    GET  /api/assessment/reports      → 评估报告列表
    GET  /api/assessment/reports/{id} → 报告详情
    GET  /api/assessment/records      → 答题记录列表
    POST /api/assessment/submit       → 提交答题结果

关联文件：
  stores/learning.ts  ← 调用本文件的函数管理评估数据
  api/index.ts        ← 底层 axios 实例

使用方式：
  import { getReports, getReport, getRecords, submitAnswer } from '@/api/assessment'
*/

import api from './index'

// 评估报告列表项
export interface AssessmentReportItem {
  id: number
  user_id: number
  report_type: string                      // diagnostic / progress / final
  dimension_scores: Record<string, number> | null
  created_at: string
}

// 评估报告详情（包含完整数据和改进建议）
export interface AssessmentReportDetail extends AssessmentReportItem {
  report_data: Record<string, unknown> | null   // 完整报告结构
  suggestions: string[] | null                  // 改进建议列表
}

// 答题记录
export interface AnswerRecord {
  id: number
  user_id: number
  question_id: number
  user_answer: string | null
  is_correct: boolean | null
  time_spent: number | null                // 答题用时（秒）
  created_at: string
}

// 提交答题的请求体
export interface SubmitAnswerData {
  question_id: number
  user_answer: string
  is_correct: boolean
  time_spent: number
}

// 获取评估报告列表
export async function getReports(): Promise<AssessmentReportItem[]> {
  const response = await api.get<AssessmentReportItem[]>('/assessment/reports')
  return response.data
}

// 获取单份评估报告的完整详情
export async function getReport(id: number): Promise<AssessmentReportDetail> {
  const response = await api.get<AssessmentReportDetail>(`/assessment/reports/${id}`)
  return response.data
}

// 获取当前用户的答题记录
export async function getRecords(): Promise<AnswerRecord[]> {
  const response = await api.get<AnswerRecord[]>('/assessment/records')
  return response.data
}

// 提交一道题的答题结果
export async function submitAnswer(data: SubmitAnswerData): Promise<AnswerRecord> {
  const response = await api.post<AnswerRecord>('/assessment/submit', data)
  return response.data
}
