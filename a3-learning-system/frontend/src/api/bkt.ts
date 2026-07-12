/*
BKT API 模块

作用：
  封装 BKT (Bayesian Knowledge Tracing) 相关的后端接口调用
  替代视图中分散的 api.get('/bkt/...') 调用

关联文件：
  views/BktCenter.vue, LearningPathView.vue, AssessmentView.vue, Dashboard.vue
*/
import api from './index'

export interface BKTStatus {
  concepts: Array<{
    concept: string
    p_known: number
    p_learn: number
    p_guess: number
    p_slip: number
    p_forget: number
    level: string
    is_mastered: boolean
  }>
  summary: {
    total: number
    mastered: number
    avg_mastery: number
  }
}

export function getBktStatus() {
  return api.get<BKTStatus>('/bkt/status')
}

export function submitAnswer(concept: string, isCorrect: boolean) {
  return api.post('/bkt/answer', { concept, is_correct: isCorrect })
}

export function runEmFit() {
  return api.post('/bkt/em-fit')
}
