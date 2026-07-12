/*
学习状态管理（Pinia Store）

作用：
  集中管理学习相关的所有数据：资源列表、评估报告、答题记录、BKT 概念、学习路径
  避免各视图各自独立拉取数据，减少重复请求
  提供统一的加载/错误状态

关联文件：
  views/Dashboard.vue       ← 读取 resources, pathPhases, bktConcepts
  views/AssessmentView.vue  ← 读取 reports, records, bktConcepts
  views/LearningPathView.vue ← 读取 pathNodes, pathEdges, pathPhases
  views/ResourceView.vue    ← 读取 resources
  api/resource.ts           ← 底层资源 API 函数
  api/assessment.ts         ← 底层评估 API 函数
  api/path.ts               ← 底层路径 API 函数

使用方式：
  import { useLearningStore } from '@/stores/learning'
  const learningStore = useLearningStore()
  await learningStore.fetchResources()
*/

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ResourceItem, ResourceDetail } from '@/api/resource'
import {
  getResources,
  getResource,
} from '@/api/resource'
import type {
  AssessmentReportItem,
  AssessmentReportDetail,
  AnswerRecord,
} from '@/api/assessment'
import {
  getReports,
  getReport,
  getRecords,
} from '@/api/assessment'
import type { LearningPath } from '@/api/path'
import { getCurrentPath } from '@/api/path'
import api from '@/api/index'

// ═══════════ Extended Types ═══════════

// BKT 知识点掌握状态（来自 /api/bkt/status）
export interface BktConcept {
  name: string
  p_known: number
  level: string
  levelClass: string
}

// 知识图谱节点（来自 /api/path/graph）
export interface GraphNode {
  id: string
  label: string
  status: 'mastered' | 'learning' | 'recommended' | 'future'
  mastery?: number
  deps: string[]
  dependents: string[]
}

// 知识图谱边
export interface GraphEdge {
  source: string
  target: string
}

// 学习路径阶段
export interface PathPhase {
  title: string
  nodes: Array<{ label: string; status: string }>
  done: boolean
  current: boolean
  estimatedHours: number
  estimatedWeeks?: number
}

// 简化的阶段数据（Dashboard 用）
export interface SimplePhase {
  name: string
  count: number
}

// 评估报告列表项（重导出，方便外部统一引用）
export type { ResourceItem, ResourceDetail }
export type { AssessmentReportItem, AssessmentReportDetail, AnswerRecord }
export type { LearningPath }

// ═══════════ Store Definition ═══════════

export const useLearningStore = defineStore('learning', () => {
  // ============ Resources State ============
  const resources = ref<ResourceItem[]>([])
  const resourcesLoading = ref(false)
  const resourcesError = ref('')

  // ============ Assessments State ============
  const reports = ref<AssessmentReportItem[]>([])
  const records = ref<AnswerRecord[]>([])
  const bktConcepts = ref<BktConcept[]>([])
  const assessmentsLoading = ref(false)
  const assessmentsError = ref('')

  // ============ Learning Path State ============
  const pathData = ref<LearningPath | null>(null)
  const graphNodes = ref<GraphNode[]>([])
  const graphEdges = ref<GraphEdge[]>([])
  const pathPhases = ref<SimplePhase[]>([])
  const pathLoading = ref(false)
  const pathError = ref('')

  // ============ Knowledge Base Stats ============
  const kbCount = ref(0)
  const exCount = ref(0)

  // ============ Computed ============
  const hasResources = computed(() => resources.value.length > 0)
  const hasAssessments = computed(() => reports.value.length > 0 || records.value.length > 0)
  const hasPath = computed(() => graphNodes.value.length > 0)
  const isEmpty = computed(() => !hasResources.value && !hasAssessments.value && !hasPath.value)

  // ============ Resource Actions ============

  async function fetchResources(size?: number): Promise<ResourceItem[]> {
    resourcesLoading.value = true
    resourcesError.value = ''
    try {
      const items = await getResources({ size: size || 50 })
      resources.value = items
      return items
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      resourcesError.value = err?.response?.data?.detail || err?.message || '加载资源失败'
      return []
    } finally {
      resourcesLoading.value = false
    }
  }

  async function fetchResourceDetail(id: number): Promise<ResourceDetail | null> {
    try {
      return await getResource(id)
    } catch {
      return null
    }
  }

  // ============ Assessment Actions ============

  async function fetchAssessments(): Promise<void> {
    assessmentsLoading.value = true
    assessmentsError.value = ''
    try {
      const [reportsData, recordsData, bktData] = await Promise.all([
        getReports(),
        getRecords(),
        api.get('/bkt/status').then(r => r.data).catch(() => null),
      ])

      reports.value = reportsData || []
      records.value = recordsData || []

      // BKT concepts
      if (bktData?.concepts && Array.isArray(bktData.concepts)) {
        bktConcepts.value = (bktData.concepts as Array<{ name: string; p_known?: number }>).map(c => ({
          name: c.name,
          p_known: c.p_known || 0,
          level: levelName(c.p_known || 0),
          levelClass: levelClass(c.p_known || 0),
        }))
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      assessmentsError.value = err?.response?.data?.detail || err?.message || '加载评估数据失败'
    } finally {
      assessmentsLoading.value = false
    }
  }

  async function fetchReportDetail(id: number): Promise<AssessmentReportDetail | null> {
    try {
      return await getReport(id)
    } catch {
      return null
    }
  }

  // ============ Learning Path Actions ============

  async function fetchLearningPath(): Promise<void> {
    pathLoading.value = true
    pathError.value = ''
    try {
      const [graphRes, pathRes] = await Promise.all([
        api.get('/path/graph'),
        getCurrentPath(),
      ])

      const graph = graphRes.data

      // Parse graph nodes/edges
      if (graph && graph.status !== 'empty') {
        const rawNodes = graph.nodes || []
        const rawEdges = graph.edges || []

        const mergedNodes: GraphNode[] = rawNodes.map(
          (n: { name?: string; id?: string; mastery?: number }) => {
            const masteryVal = n.mastery || 0
            let status: GraphNode['status'] = 'future'
            if (masteryVal >= 85) status = 'mastered'
            else if (masteryVal >= 50) status = 'learning'
            else if (masteryVal > 0) status = 'recommended'
            return {
              id: n.name || n.id || `node_${Math.random()}`,
              label: n.name || n.id || '',
              status,
              mastery: masteryVal > 0 ? masteryVal : undefined,
              deps: [],
              dependents: [],
            }
          },
        )

        // Build dependency maps
        rawEdges.forEach((e: { source?: string; from?: string; target?: string; to?: string }) => {
          const from = e.source || e.from
          const to = e.target || e.to
          const fromNode = mergedNodes.find(n => n.id === from || n.label === from)
          const toNode = mergedNodes.find(n => n.id === to || n.label === to)
          if (fromNode && toNode) {
            if (!toNode.deps.includes(fromNode.label)) toNode.deps.push(fromNode.label)
            if (!fromNode.dependents.includes(toNode.label)) fromNode.dependents.push(toNode.label)
          }
        })

        // Auto-recommend nodes whose deps are all mastered
        mergedNodes.forEach(n => {
          if (n.status === 'future' && n.deps.length > 0) {
            const allDepsMastered = n.deps.every(d => {
              const dep = mergedNodes.find(nd => nd.label === d)
              return dep && dep.status === 'mastered'
            })
            if (allDepsMastered) n.status = 'recommended'
          }
        })

        graphNodes.value = mergedNodes

        graphEdges.value = rawEdges.map(
          (e: { source?: string; from?: string; target?: string; to?: string }) => ({
            source: e.source || e.from || '',
            target: e.target || e.to || '',
          }),
        )
      }

      // Parse phases from /api/path/current
      pathData.value = pathRes
      // The API returns phases at the top level of the response data
      const rawPhases = (pathRes as unknown as { phases?: Array<{ phase: number; topics: string[]; count: number }> })?.phases
      if (rawPhases && rawPhases.length > 0) {
        pathPhases.value = rawPhases.map(p => ({
          name: `阶段 ${p.phase}`,
          count: p.count,
        }))
      } else if (graphNodes.value.length > 0) {
        // Fallback: compute from graph nodes (topological sort)
        pathPhases.value = computePathPhases()
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      pathError.value = err?.response?.data?.detail || err?.message || '加载学习路径失败'
    } finally {
      pathLoading.value = false
    }
  }

  // ============ KB Stats Action ============

  async function fetchKBStats(): Promise<void> {
    try {
      const res = await api.get('/admin/stats')
      kbCount.value = res.data?.knowledge_base || 0
      exCount.value = res.data?.exercise_bank || 0
    } catch {
      // 知识库统计加载失败不影响主要功能
    }
  }

  // ============ Utilities ============

  function computePathPhases(): SimplePhase[] {
    const nodes = graphNodes.value
    if (nodes.length === 0) return []

    const inDegree: Record<string, number> = {}
    nodes.forEach(n => { inDegree[n.id] = n.deps.length })
    const remaining = new Set(nodes.map(n => n.id))
    const result: { nodes: GraphNode[] }[] = []

    while (remaining.size > 0) {
      const current = [...remaining].filter(id => inDegree[id] === 0)
      if (current.length === 0) break
      const phaseNodes = current.map(id => nodes.find(n => n.id === id)!).filter(Boolean)
      result.push({ nodes: phaseNodes })
      current.forEach(id => {
        remaining.delete(id)
        const node = nodes.find(n => n.id === id)
        if (node) {
          node.dependents.forEach(dep => {
            if (inDegree[dep] > 0) inDegree[dep]--
          })
        }
      })
    }

    return result.map((phase, i) => ({
      name: `阶段 ${i + 1}`,
      count: phase.nodes.length,
    }))
  }

  function levelClass(p: number): string {
    if (p >= 0.85) return 'mastered'
    if (p >= 0.6) return 'learning'
    if (p >= 0.35) return 'familiar'
    return 'beginner'
  }

  function levelName(p: number): string {
    if (p >= 0.85) return '精通'
    if (p >= 0.6) return '熟悉'
    if (p >= 0.35) return '学习中'
    return '入门'
  }

  // ============ Clear Cache ============

  function clearCache() {
    resources.value = []
    reports.value = []
    records.value = []
    bktConcepts.value = []
    pathData.value = null
    graphNodes.value = []
    graphEdges.value = []
    pathPhases.value = []
    kbCount.value = 0
    exCount.value = 0
    resourcesError.value = ''
    assessmentsError.value = ''
    pathError.value = ''
  }

  // ============ Expose ============

  return {
    // State
    resources, resourcesLoading, resourcesError,
    reports, records, bktConcepts, assessmentsLoading, assessmentsError,
    pathData, graphNodes, graphEdges, pathPhases, pathLoading, pathError,
    kbCount, exCount,

    // Computed
    hasResources, hasAssessments, hasPath, isEmpty,

    // Actions
    fetchResources,
    fetchResourceDetail,
    fetchAssessments,
    fetchReportDetail,
    fetchLearningPath,
    fetchKBStats,
    clearCache,
  }
})
