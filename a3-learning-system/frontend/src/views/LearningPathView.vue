<template>
  <div class="kg-center">
    <!-- ═══════════ HEADER ═══════════ -->
    <div class="kg-top">
      <div class="kg-top-l">
        <h1>知识图谱学习中心</h1>
        <p>基于知识图谱<strong>拓扑排序</strong>的动态学习路径规划 — 力导向布局，支持缩放拖拽</p>
        <span v-if="domainName" class="kg-domain-badge">{{ domainName }}</span>
        <span v-if="previewMode" class="kg-preview-badge">预览模式 — 对话后自动匹配领域</span>
      </div>
      <div class="kg-top-r">
        <!-- 领域选择器（参考美团：用户可切换不同领域图谱） -->
        <el-select
          v-model="currentDomain"
          placeholder="切换学习领域"
          size="small"
          style="width: 180px; margin-right: 8px;"
          @change="switchDomain"
        >
          <el-option
            v-for="d in availableDomains"
            :key="d.id"
            :label="d.name"
            :value="d.id"
          >
            <span style="font-weight: 600;">{{ d.name }}</span>
            <span v-if="d.books && d.books.length" style="color: #9CA3AF; font-size: 11px; margin-left: 6px;">
              ({{ d.books.slice(0,2).join('/') }})
            </span>
          </el-option>
        </el-select>

        <el-button size="small" :type="presentMode ? 'warning' : 'default'" @click="presentMode = !presentMode">
          <el-icon :size="14"><VideoPlay /></el-icon> {{ presentMode ? '退出演示' : '答辩模式' }}
        </el-button>
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="graph">Graph 视图</el-radio-button>
          <el-radio-button value="timeline">阶段视图</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- ═══════════ Legend Bar ═══════════ -->
    <div class="kg-legend">
      <div v-for="l in legendItems" :key="l.label" class="legend-chip">
        <span class="legend-dot" :style="{ background: l.color }" />
        <span>{{ l.label }}</span>
        <span class="legend-count">({{ l.count }})</span>
      </div>
      <span class="legend-hint">滚轮缩放 / 拖拽平移 / 悬停高亮关联节点 / 点击查看详情</span>
    </div>

    <!-- ═══════════ MAIN CONTENT ═══════════ -->
    <!-- Loading State -->
    <div v-if="loading" class="kg-loading">
      <el-icon class="spin" :size="36"><Loading /></el-icon>
      <p>加载知识图谱数据...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="kg-empty">
      <el-empty :description="error">
        <el-button type="primary" @click="loadData">重新加载</el-button>
      </el-empty>
    </div>

    <!-- Normal Content（永远展示图谱，不再有空白引导页） -->
    <div v-else class="kg-main">
      <!-- Graph View (ECharts Force-Directed Graph) -->
      <div v-show="viewMode === 'graph'" class="kg-graph-wrap">
        <div ref="chartRef" class="kg-chart" />
      </div>

      <!-- Timeline View -->
      <div v-show="viewMode === 'timeline'" class="kg-timeline-wrap">
        <div class="timeline-track">
          <div
            v-for="(phase, pi) in phases"
            :key="pi"
            class="tl-phase"
          >
            <div class="tl-phase-marker" :class="{ done: phase.done, current: phase.current }">
              <span>{{ pi + 1 }}</span>
            </div>
            <div class="tl-phase-line" v-if="pi < phases.length - 1" :class="{ active: phase.done }" />
            <div class="tl-phase-card">
              <div class="tl-phase-title">{{ phase.title }}</div>
              <div class="tl-phase-nodes">
                <span
                  v-for="n in phase.nodes"
                  :key="n.label"
                  class="tl-node-tag"
                  :class="n.status"
                >{{ n.label }}</span>
              </div>
              <div class="tl-phase-meta">
                <span>{{ phase.estimatedHours }}h 预计</span>
                <span v-if="phase.estimatedWeeks">{{ phase.estimatedWeeks }}周</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right Panel -->
      <aside class="kg-right">
        <!-- Selection Detail -->
        <div class="kg-panel">
          <div class="kg-panel-hd">节点详情</div>
          <div class="kg-panel-bd">
            <template v-if="selectedNode">
              <div class="detail-name">{{ selectedNode.label }}</div>
              <div class="detail-status" :class="selectedNode.status">{{ selectedNode.labelZh || statusLabel(selectedNode.status) }}</div>
              <div class="detail-mastery">
                <div class="detail-mastery-bar">
                  <div class="detail-mastery-fill" :style="{ width: Math.round(selectedNode.p_known * 100) + '%', background: selectedNode.color }" />
                </div>
                <span>BKT p={{ selectedNode.p_known.toFixed(3) }} ({{ Math.round(selectedNode.p_known * 100) }}% 掌握)</span>
              </div>
              <div v-if="selectedNode.deps && selectedNode.deps.length" class="detail-deps">
                <div class="detail-subtitle">前置依赖</div>
                <span v-for="d in selectedNode.deps" :key="d" class="dep-tag">{{ d }}</span>
              </div>
              <div v-if="selectedNode.dependents && selectedNode.dependents.length" class="detail-deps">
                <div class="detail-subtitle">后续依赖此知识点</div>
                <span v-for="d in selectedNode.dependents" :key="d" class="dep-tag future">{{ d }}</span>
              </div>
            </template>
            <div v-else class="detail-empty">点击节点查看详情</div>
          </div>
        </div>

        <!-- Stats -->
        <div class="kg-panel">
          <div class="kg-panel-hd">学习统计</div>
          <div class="kg-panel-bd">
            <div class="kg-stat-row">
              <span class="kg-stat-label">知识点总数</span>
              <span class="kg-stat-val">{{ totalNodes }}</span>
            </div>
            <div class="kg-stat-row">
              <span class="kg-stat-label">已掌握</span>
              <span class="kg-stat-val green">{{ masteredCount }}</span>
            </div>
            <div class="kg-stat-row">
              <span class="kg-stat-label">学习中</span>
              <span class="kg-stat-val blue">{{ learningCount }}</span>
            </div>
            <div class="kg-stat-row">
              <span class="kg-stat-label">待学习</span>
              <span class="kg-stat-val muted">{{ pendingCount }}</span>
            </div>
            <div class="kg-stat-row total">
              <span class="kg-stat-label">预计总学习时间</span>
              <span class="kg-stat-val">{{ totalHours }}h</span>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import api from '@/api/index'

// ═══════════ Types ═══════════
interface KGNode {
  id: string; label: string
  /** BKT 掌握等级: mastered / learning / familiar / beginner / unknown */
  status: 'mastered' | 'learning' | 'familiar' | 'beginner' | 'unknown'
  /** 中文标签（从后端获取） */
  labelZh: string
  /** BKT 掌握概率 0-1 */
  p_known: number
  /** 来自后端 BKT 映射的颜色 */
  color: string
  /** 来自后端 BKT 映射的节点大小 */
  size: number
  /** 知识点所属阶段分组 */
  phase?: string
  deps: string[]; dependents: string[]
}
interface Phase {
  title: string; nodes: { label: string; status: string }[]
  done: boolean; current: boolean; estimatedHours: number; estimatedWeeks?: number
}
interface DomainOption {
  id: string; name: string; books?: string[]
}

// ═══════════ State ═══════════
const viewMode = ref<'graph' | 'timeline'>('graph')
const presentMode = ref(false)
const loading = ref(true)
const error = ref('')
const domainName = ref('')
const previewMode = ref(false)
const currentDomain = ref('')
const selectedNode = ref<KGNode | null>(null)
const nodes = ref<KGNode[]>([])
const phases = ref<Phase[]>([])
const availableDomains = ref<DomainOption[]>([])

// ECharts 实例
const chartRef = ref<HTMLDivElement>()
let chartInstance: echarts.ECharts | null = null

// ═══════════ Computed ═══════════
const legendItems = computed(() => [
  { label: '精通', color: '#10B981', count: nodes.value.filter(n => n.status === 'mastered').length },
  { label: '熟悉', color: '#2563EB', count: nodes.value.filter(n => n.status === 'learning').length },
  { label: '学习中', color: '#F59E0B', count: nodes.value.filter(n => n.status === 'familiar').length },
  { label: '入门', color: '#8B5CF6', count: nodes.value.filter(n => n.status === 'beginner').length },
  { label: '未学习', color: '#94A3B8', count: nodes.value.filter(n => n.status === 'unknown').length },
])
const totalNodes = computed(() => nodes.value.length)
const masteredCount = computed(() => nodes.value.filter(n => n.status === 'mastered').length)
const learningCount = computed(() => nodes.value.filter(n => n.status === 'learning' || n.status === 'familiar').length)
const pendingCount = computed(() => nodes.value.filter(n => n.status === 'beginner' || n.status === 'unknown').length)
const totalHours = computed(() => phases.value.reduce((s, p) => s + p.estimatedHours, 0))

// ═══════════ Helpers ═══════════
function statusLabel(s: string) {
  const m: Record<string,string> = { mastered:'精通', learning:'熟悉', familiar:'学习中', beginner:'入门', unknown:'未学习' }
  return m[s] || s
}
function nodeColor(s: string) {
  const m: Record<string,string> = { mastered:'#1D4ED8', learning:'#2563EB', familiar:'#60A5FA', beginner:'#93C5FD', unknown:'#94A3B8' }
  return m[s] || '#94A3B8'
}
function nodeSize(s: string): number {
  const m: Record<string,number> = { mastered:28, learning:26, familiar:22, beginner:18, unknown:16 }
  return m[s] || 16
}
/** 基于 p_known 的动态节点大小：掌握度越高节点越大 (16-30px 范围) */
function dynamicNodeSize(p_known: number): number {
  if (p_known <= 0) return 16
  return Math.round(16 + p_known * 14)
}

// ═══════════ 切换领域 ═══════════
async function switchDomain(domainId: string) {
  if (!domainId) return
  loading.value = true
  error.value = ''
  try {
    const res = await api.get(`/path/graph/${domainId}`)
    handleGraphData(res.data)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    error.value = err?.response?.data?.detail || err?.message || '切换领域失败'
  } finally {
    loading.value = false
  }
}

// ═══════════ ECharts 力导向图渲染 ═══════════
function selectNode(n: KGNode) { selectedNode.value = n }

function renderGraph() {
  if (!chartRef.value || nodes.value.length === 0) return

  // 销毁旧实例
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }

  chartInstance = echarts.init(chartRef.value)

  // 构建节点数据（ECharts graph 格式，使用后端 BKT 映射的颜色和大小）
  const chartNodes = nodes.value.map(n => ({
    id: n.id,
    name: n.label,
    symbolSize: dynamicNodeSize(n.p_known),
    value: n.p_known,
    itemStyle: {
      color: n.color,
      borderColor: n.status === 'familiar' && n.p_known > 0 ? '#93C5FD' : 'transparent',
      borderWidth: n.status === 'familiar' && n.p_known > 0 ? 2 : 0,
      shadowBlur: n.status === 'mastered' ? 10 : (n.status === 'learning' ? 6 : 0),
      shadowColor: n.status === 'mastered' ? 'rgba(29,78,216,0.3)' : (n.status === 'learning' ? 'rgba(37,99,235,0.25)' : 'transparent'),
    },
    label: {
      show: true,
      fontSize: n.status === 'unknown' ? 11 : 12,
      fontWeight: n.status === 'mastered' || n.status === 'learning' ? 600 : 400,
      color: n.status === 'unknown' ? '#9CA3AF' : '#374151',
    },
    category: n.status === 'mastered' ? 0 : n.status === 'learning' ? 1 : n.status === 'familiar' ? 2 : n.status === 'beginner' ? 3 : 4,
  }))

  // 构建边数据
  const chartLinks: Array<{ source: string; target: string }> = []
  nodes.value.forEach(n => {
    n.deps.forEach(dep => {
      const sourceNode = nodes.value.find(nd => nd.label === dep || nd.id === dep)
      if (sourceNode) {
        chartLinks.push({ source: sourceNode.id, target: n.id })
      }
    })
  })

  // 类别定义（用于着色和 Legend—5 级 BKT 掌握度）
  const categories = [
    { name: '精通', itemStyle: { color: '#1D4ED8' } },
    { name: '熟悉', itemStyle: { color: '#2563EB' } },
    { name: '学习中', itemStyle: { color: '#60A5FA' } },
    { name: '入门', itemStyle: { color: '#93C5FD' } },
    { name: '未学习', itemStyle: { color: '#94A3B8' } },
  ]

  const option: echarts.EChartsOption = {
    backgroundColor: 'transparent',
    title: { show: false },
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        if (params.dataType === 'node') {
          const node = nodes.value.find(n => n.id === params.data.id)
          if (!node) return params.data.name
          const pct = Math.round(node.p_known * 100)
          return `<b>${node.label}</b><br/>等级：${node.labelZh || statusLabel(node.status)}<br/>掌握概率：${pct}% (BKT p=${node.p_known.toFixed(3)})`
        }
        return ''
      },
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#E5E7EB',
      borderWidth: 1,
      textStyle: { color: '#374151', fontSize: 12 },
      extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-radius: 8px;',
    },
    animationDurationUpdate: 500,
    animationEasingUpdate: 'quarticIn',
    series: [{
      type: 'graph',
      layout: 'force',
      data: chartNodes,
      links: chartLinks,
      categories,
      roam: true,           // 开启缩放+拖拽
      draggable: true,      // 节点可拖拽
      focusNodeAdjacency: true, // 鼠标悬停高亮关联节点和边
      force: {
        repulsion: 200,     // 节点间斥力（越大越分散）
        edgeLength: [80, 200], // 边的长度范围
        gravity: 0.1,       // 向中心的引力
        friction: 0.6,      // 摩擦系数（越大越快停止）
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3 },
        itemStyle: { shadowBlur: 20, shadowColor: 'rgba(59,130,246,0.4)' },
      },
      lineStyle: {
        color: 'source',
        curveness: 0.15,    // 微弯曲让连线更自然
        width: 1.5,
        opacity: 0.35,
      },
      label: {
        position: 'bottom',
        formatter: '{b}',
      },
      edgeLabel: { show: false },
    }],
  }

  chartInstance.setOption(option)

  // 节点点击事件
  chartInstance.on('click', (params: any) => {
    if (params.dataType === 'node') {
      const node = nodes.value.find(n => n.id === params.data.id)
      if (node) selectNode(node)
    }
  })

  // 响应式 resize
  window.addEventListener('resize', handleResize)
}

function handleResize() {
  chartInstance?.resize()
}

// ═══════════ 处理API返回的图谱数据 ═══════════
function handleGraphData(graph: any) {
  domainName.value = graph.domain_name || ''
  previewMode.value = !!graph.preview_mode
  currentDomain.value = graph.domain || ''

  // 可用领域列表
  if (graph.available_domains) {
    availableDomains.value = graph.available_domains
  }

  const rawNodes = graph.nodes || []
  const rawEdges = graph.edges || []

  if (rawNodes.length === 0) {
    error.value = graph.message || '该领域暂无图谱数据'
    nodes.value = []; phases.value = []
    if (chartInstance) { chartInstance.dispose(); chartInstance = null }
    return
  }

  // Convert to KGNode format using BKT data from backend
  // Backend now returns: name, id, p_known, level, label_zh, color, size, phase
  const mergedNodes: KGNode[] = rawNodes.map((n: any) => {
    const name = n.name || n.id || `node_${Math.random()}`
    const pKnown: number = typeof n.p_known === 'number' ? n.p_known : 0
    // 直接使用后端返回的 level（基于 BKT p_known 正确阈值映射）
    const level = n.level || 'unknown'
    const apiColor = n.color || '#94A3B8'
    const apiSize = n.size || 16
    const labelZh = n.label_zh || ''
    const phase = n.phase || ''

    return {
      id: name,
      label: name,
      status: level as KGNode['status'],
      labelZh,
      p_known: pKnown,
      color: apiColor,
      size: apiSize,
      phase,
      deps: [], dependents: [],
    }
  })

  // Build dependency maps from edges
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

  // Highlight unlockable nodes: beginner/unknown nodes whose deps are all mastered/learning
  mergedNodes.forEach(n => {
    if ((n.status === 'beginner' || n.status === 'unknown') && n.deps.length > 0) {
      const allDepsClear = n.deps.every(d => {
        const dep = mergedNodes.find(nd => nd.label === d)
        return dep && (dep.status === 'mastered' || dep.status === 'learning')
      })
      if (allDepsClear) {
        // Upgrade visual to familiar level (dashed border in rendering)
        n.status = 'familiar'
        n.color = '#60A5FA'
        if (n.size < 22) n.size = 22
      }
    }
  })

  nodes.value = mergedNodes

  // Render ECharts graph after DOM update
  nextTick(() => renderGraph())

  computePhases()
}

// ═══════════ 阶段计算（拓扑排序） ═══════════
function computePhases() {
  const inDegree: Record<string, number> = {}
  nodes.value.forEach(n => { inDegree[n.id] = n.deps.length })
  const remaining = new Set(nodes.value.map(n => n.id))
  const result: Phase[] = []
  let phaseNum = 1

  while (remaining.size > 0) {
    const current = [...remaining].filter(id => inDegree[id] === 0)
    if (current.length === 0) break

    const phaseNodes = current.map(id => nodes.value.find(n => n.id === id)!).filter(Boolean)
    const done = phaseNodes.every(n => n.status === 'mastered')
    const anyDone = phaseNodes.some(n => n.status === 'mastered' || n.status === 'learning')

    result.push({
      title: `阶段 ${phaseNum}`,
      nodes: phaseNodes.map(n => ({ label: n.label, status: n.status })),
      done,
      current: anyDone && !done,
      estimatedHours: phaseNodes.length * 1.5,
      estimatedWeeks: phaseNum <= 2 ? phaseNum : undefined,
    })

    current.forEach(id => {
      remaining.delete(id)
      const node = nodes.value.find(n => n.id === id)
      if (node) node.dependents.forEach(dep => { if (inDegree[dep] > 0) inDegree[dep]-- })
    })
    phaseNum++
  }
  phases.value = result
}

// ═══════════ Data Loading ═══════════
async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const graphRes = await api.get('/path/graph')
    handleGraphData(graphRes.data)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    error.value = err?.response?.data?.detail || err?.message || '知识图谱数据加载失败'
    nodes.value = []; computePhases()
  } finally {
    loading.value = false
  }
}

// ═══════════ Presentation Mode ═══════════
let presentTimer: ReturnType<typeof setInterval> | undefined
function startPresentation() {
  let i = 0
  const recs = nodes.value.filter(n => n.status === 'beginner' || n.status === 'familiar')
  presentTimer = setInterval(() => {
    if (recs.length === 0 || !chartInstance) return
    const node = recs[i % recs.length]
    selectedNode.value = node
    chartInstance!.dispatchAction({
      type: 'highlight',
      seriesIndex: 0,
      dataIndex: nodes.value.findIndex(n => n.id === node.id),
    })
    i++
  }, 2500)
}

watch(presentMode, (on) => {
  if (on) startPresentation()
  else {
    if (presentTimer !== undefined) clearInterval(presentTimer)
    presentTimer = undefined
    selectedNode.value = null
    if (chartInstance) chartInstance.dispatchAction({ type: 'downplay', seriesIndex: 0 })
  }
})

onMounted(loadData)
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (presentTimer !== undefined) clearInterval(presentTimer)
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }
})
</script>

<style scoped>
/* ═════════ Layout ═════════ */
.kg-center {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
  min-height: calc(100vh - 120px);
}
.kg-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
  gap: 16px;
  flex-wrap: wrap;
}
.kg-top-l h1 {
  font-size: 22px;
  font-weight: 700;
  color: #111827;
  margin: 0 0 4px 0;
}
.kg-top-l p {
  color: #6B7280;
  font-size: 13px;
  margin: 0;
}
.kg-domain-badge {
  display: inline-block;
  background: linear-gradient(135deg, #EFF6FF, #DBEAFE);
  color: #1D4ED8;
  padding: 3px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  margin-top: 6px;
}
.kg-preview-badge {
  display: inline-block;
  background: #FEF3C7;
  color: #92400E;
  padding: 3px 12px;
  border-radius: 20px;
  font-size: 11px;
  margin-top: 6px;
  margin-left: 6px;
}
.kg-top-r {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* Legend */
.kg-legend {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.legend-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: #4B5563;
}
.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.legend-count {
  color: #9CA3AF;
  font-size: 11px;
}
.legend-hint {
  margin-left: auto;
  color: #9CA3AF;
  font-size: 11px;
}

/* Loading */
.kg-loading {
  text-align: center;
  padding: 80px 20px;
  color: #6B7280;
}
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Error */
.kg-empty {
  text-align: center;
  padding: 60px 20px;
}

/* Main */
.kg-main {
  display: flex;
  gap: 16px;
  position: relative;
}
.kg-graph-wrap {
  flex: 1;
  min-height: 520px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 50%, rgba(59,130,246,0.03) 0%, transparent 70%),
    var(--bg-card);
}
.kg-chart {
  width: 100%;
  height: 100%;
  min-height: 520px;
}

/* Right Panel */
.kg-right {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.kg-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
}
.kg-panel-hd {
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 600;
  color: #374151;
  border-bottom: 1px solid var(--border-color);
  background: #F9FAFB;
}
.kg-panel-bd { padding: 14px; }

.detail-name {
  font-size: 16px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 6px;
}
.detail-status {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 10px;
}
.detail-status.mastered { background: #DBEAFE; color: #1D4ED8; }
.detail-status.learning { background: #BFDBFE; color: #2563EB; }
.detail-status.familiar { background: #EFF6FF; color: #60A5FA; }
.detail-status.beginner { background: #F0F9FF; color: #93C5FD; }
.detail-status.unknown { background: #F3F4F6; color: #6B7280; }
.detail-mastery {
  margin-bottom: 12px;
}
.detail-mastery-bar {
  height: 6px;
  background: #E5E7EB;
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 4px;
}
.detail-mastery-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}
.detail-mastery span {
  font-size: 12px;
  color: #6B7280;
}
.detail-deps { margin-bottom: 10px; }
.detail-subtitle {
  font-size: 11px;
  font-weight: 600;
  color: #6B7280;
  margin-bottom: 4px;
}
.dep-tag {
  display: inline-block;
  padding: 2px 8px;
  background: #EFF6FF;
  color: #2563EB;
  border-radius: 10px;
  font-size: 11px;
  margin: 2px 3px 0 0;
}
.dep-tag.future {
  background: #F3F4F6;
  color: #9CA3AF;
}
.detail-empty {
  color: #9CA3AF;
  font-size: 13px;
  text-align: center;
  padding: 20px 0;
}

/* Stats */
.kg-stat-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 13px;
  border-bottom: 1px dashed #F3F4F6;
}
.kg-stat-row:last-child { border-bottom: none; }
.kg-stat-label { color: #6B7280; }
.kg-stat-val { font-weight: 600; color: #111827; }
.kg-stat-val.green { color: #059669; }
.kg-stat-val.blue { color: #2563EB; }
.kg-stat-val.muted { color: #9CA3AF; }
.kg-stat-row.total { font-weight: 600; border-bottom: none; border-top: 1px solid #E5E7EB; margin-top: 4px; padding-top: 8px; }

/* Timeline */
.kg-timeline-wrap {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.timeline-track { position: relative; padding-left: 40px; }
.tl-phase { position: relative; padding-bottom: 24px; }
.tl-phase-marker {
  position: absolute;
  left: -36px;
  top: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #E5E7EB;
  color: #9CA3AF;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  border: 3px solid white;
  box-shadow: 0 0 0 2px #E5E7EB;
}
.tl-phase-marker.done {
  background: #1D4ED8;
  color: white;
  box-shadow: 0 0 0 2px #1D4ED8;
}
.tl-phase-marker.current {
  background: #F59E0B;
  color: white;
  box-shadow: 0 0 0 2px #F59E0B;
}
.tl-phase-line {
  position: absolute;
  left: -24px;
  top: 24px;
  width: 2px;
  height: calc(100% - 18px);
  background: #E5E7EB;
}
.tl-phase-line.active { background: #1D4ED8; }
.tl-phase-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px 16px;
}
.tl-phase-title {
  font-weight: 600;
  font-size: 14px;
  color: #111827;
  margin-bottom: 8px;
}
.tl-phase-nodes { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.tl-node-tag {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  background: #F3F4F6;
  color: #6B7280;
}
.tl-node-tag.mastered { background: #DBEAFE; color: #1D4ED8; }
.tl-node-tag.learning { background: #BFDBFE; color: #2563EB; }
.tl-node-tag.familiar { background: #EFF6FF; color: #60A5FA; }
.tl-node-tag.beginner { background: #F0F9FF; color: #93C5FD; }
.tl-node-tag.unknown { background: #F3F4F6; color: #94A3B8; }
.tl-phase-meta { font-size: 11px; color: #9CA3AF; }
.tl-phase-meta span + span::before { content: ' · '; }
</style>
