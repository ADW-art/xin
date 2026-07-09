<template>
  <div class="cg-layout">
    <!-- ═══ 左侧：图谱主区域 ═══ -->
    <div class="cg-main">
      <!-- Toolbar -->
      <div class="cg-toolbar">
        <div class="cg-toolbar-left">
          <el-select v-model="selectedId" placeholder="选择或新建图谱" size="default" style="width:240px" @change="onSelect" clearable :loading="listLoading" no-data-text="暂无图谱数据">
            <el-option v-for="g in graphs" :key="g.id" :label="g.title + ' (' + g.node_count + '节点)'" :value="g.id" />
          </el-select>
          <el-button type="primary" size="small" @click="dlgCreate = true">+ 新建</el-button>
          <el-button size="small" @click="onSelect" :disabled="!selectedId">刷新</el-button>
          <el-button type="danger" plain size="small" @click="onDelete" :disabled="!selectedId">删除</el-button>
        </div>
        <div class="cg-toolbar-right">
          <el-button v-if="graphData" type="success" size="small" @click="onSave" :loading="saving">
            保存图谱
          </el-button>
          <span v-if="saved" class="cg-saved"><el-icon color="#10B981"><CircleCheckFilled /></el-icon> 已保存</span>
        </div>
      </div>

      <!-- 错误提示 -->
      <div v-if="listError" class="cg-error-bar">
        <span>{{ listError }}</span>
        <el-button size="small" type="primary" link @click="loadList">重试</el-button>
      </div>

      <!-- 未登录 -->
      <div v-if="!token" class="cg-empty-state">
        <p>请先登录后使用自定义知识图谱</p>
        <el-button type="primary" @click="$router.push('/login')">去登录</el-button>
      </div>

      <!-- 已登录 + 有图谱数据 -->
      <template v-else-if="graphData">
        <!-- 图谱标题 -->
        <div class="cg-graph-title">
          <h3>{{ graphData.title }}</h3>
          <span class="cg-sub">{{ (graphData.nodes||[]).length }} 个节点 · {{ (graphData.edges||[]).length }} 条连线</span>
        </div>

        <!-- 添加节点 / 添加连线 / 编辑 行 -->
        <div class="cg-op-bar">
          <template v-if="opMode === 'addNode'">
            <el-input v-model="nodeName" placeholder="知识点名称" size="default" style="width:180px" clearable @keydown.enter="addNode" />
            <el-select v-model="nodePhase" size="default" style="width:130px">
              <el-option v-for="p in phases" :key="p.value" :label="p.label" :value="p.value">
                <span :style="{display:'inline-block',width:8,height:8,borderRadius:'50%',background:phaseColorMap[p.value],marginRight:6}"></span>{{ p.label }}
              </el-option>
            </el-select>
            <el-button type="primary" size="small" @click="addNode" :disabled="!nodeName.trim()">+ 节点</el-button>
            <el-button size="small" @click="opMode='addEdge'">→ 改为连线</el-button>
          </template>
          <template v-else-if="opMode === 'addEdge'">
            <el-select v-model="edgeSource" placeholder="起点" size="default" style="width:140px" clearable>
              <el-option v-for="(n,i) in (graphData.nodes||[])" :key="i" :label="n.name" :value="i" />
            </el-select>
            <span style="color:#94a3b8;font-size:16px">→</span>
            <el-select v-model="edgeTarget" placeholder="终点" size="default" style="width:140px" clearable>
              <el-option v-for="(n,i) in (graphData.nodes||[])" :key="i" :label="n.name" :value="i" />
            </el-select>
            <el-button type="warning" size="small" @click="addEdge" :disabled="edgeSource===null||edgeTarget===null||edgeSource===edgeTarget">+ 连线</el-button>
            <el-button size="small" @click="opMode='addNode'">→ 改为添加节点</el-button>
          </template>
          <template v-else-if="opMode === 'editNode' && editingIndex !== null">
            <el-input v-model="editName" placeholder="名称" size="default" style="width:160px" @keydown.enter="saveEdit" />
            <el-select v-model="editPhase" size="default" style="width:120px">
              <el-option v-for="p in phases" :key="p.value" :label="p.label" :value="p.value" />
            </el-select>
            <el-button type="success" size="small" @click="saveEdit">确认</el-button>
            <el-button size="small" @click="cancelEdit">取消</el-button>
          </template>
        </div>

        <!-- ECharts 力导向图（与系统图谱一致） -->
        <div v-if="graphLoading" class="cg-chart" style="display:flex;align-items:center;justify-content:center">
          <div style="text-align:center;color:#94a3b8">
            <el-icon class="spin" :size="32"><Loading /></el-icon>
            <p style="margin-top:8px;font-size:13px">加载图谱数据...</p>
          </div>
        </div>
        <div v-else ref="chartRef" class="cg-chart" />
      </template>

      <!-- 空状态 -->
      <div v-else class="cg-empty-state">
        <el-empty description="选择已有图谱或新建一个开始构建">
          <el-button type="primary" @click="dlgCreate=true">新建图谱</el-button>
        </el-empty>
      </div>

      <!-- 创建对话框 -->
      <el-dialog v-model="dlgCreate" title="新建知识图谱" width="420px">
        <el-form label-width="80px" size="default">
          <el-form-item label="图谱名称">
            <el-input v-model="title" placeholder="例如：数据结构复习计划" />
          </el-form-item>
          <el-form-item label="初始模板">
            <el-select v-model="domain" placeholder="可选，从系统图谱复制节点" style="width:100%" clearable>
              <el-option v-for="d in domains" :key="d.id" :label="d.name" :value="d.id" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dlgCreate=false">取消</el-button>
          <el-button type="primary" @click="onCreate" :disabled="!title.trim()">创建</el-button>
        </template>
      </el-dialog>
    </div>

    <!-- ═══ 右侧：节点详情面板（对标系统图谱） ═══ -->
    <aside v-if="selectedNode" class="cg-panel">
      <div class="cg-panel-hd">节点详情</div>
      <div class="cg-panel-bd">
        <div class="detail-name">{{ selectedNode.name }}</div>
        <div class="detail-status" :class="selectedNode.level || 'unknown'">
          {{ statusLabel(selectedNode.level) }}
        </div>
        <!-- BKT 掌握度条 -->
        <div class="detail-mastery">
          <div class="detail-mastery-bar">
            <div class="detail-mastery-fill"
                 :style="{ width: Math.round((selectedNode.p_known || 0) * 100) + '%', background: selectedNode.color || '#94A3B8' }" />
          </div>
          <span>BKT p={{ (selectedNode.p_known || 0).toFixed(3) }} ({{ Math.round((selectedNode.p_known || 0) * 100) }}% 掌握)</span>
        </div>
        <!-- 阶段信息 -->
        <div class="detail-section">
          <div class="detail-subtitle">阶段</div>
          <span class="phase-tag" :style="{ background: phaseColorMap[selectedNode.phase] || '#94A3B8' }">
            {{ phaseLabel(selectedNode.phase) }}
          </span>
        </div>
        <!-- 操作按钮 -->
        <div class="detail-actions">
          <el-button size="small" type="warning" @click="startEdit(nodeIndex!)">编辑节点</el-button>
          <el-button size="small" type="danger" plain @click="removeNode(nodeIndex!)">删除节点</el-button>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick, defineExpose } from 'vue'
import * as echarts from 'echarts'
import { CircleCheckFilled, Loading } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api/index'

// ── State ──
const token = ref(localStorage.getItem('token'))
const graphs = ref<any[]>([])
const selectedId = ref<number | null>(null)
const graphData = ref<any>(null)
const dlgCreate = ref(false)
const saving = ref(false)
const saved = ref(false)
const listError = ref('')
const listLoading = ref(false)
const graphLoading = ref(false)

// Create form
const title = ref('')
const domain = ref('')

// Op mode: 'addNode' | 'addEdge' | 'editNode'
const opMode = ref<'addNode' | 'addEdge' | 'editNode'>('addNode')

// Add node
const nodeName = ref('')
const nodePhase = ref('core')

// Add edge
const edgeSource = ref<number | null>(null)
const edgeTarget = ref<number | null>(null)

// Edit node
const editingIndex = ref<number | null>(null)
const editName = ref('')
const editPhase = ref('core')

// Selected node (for right panel)
const selectedNode = ref<any>(null)
const nodeIndex = ref<number | null>(null)

// Chart
const chartRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null

// ── Constants ──
const phases = [
  { label: '入门基础', value: 'foundation' },
  { label: '核心能力', value: 'core' },
  { label: '进阶深入', value: 'advanced' },
  { label: '工程实战', value: 'practice' },
]

/** Phase → 颜色（与系统图谱 BKT 色系一致） */
const phaseColorMap: Record<string, string> = {
  foundation: '#8B5CF6',
  core: '#2563EB',
  advanced: '#F59E0B',
  practice: '#10B981',
}

const phaseLabel = (v: string): string => {
  const p = phases.find(x => x.value === v)
  return p ? p.label : v
}

const statusLabel = (level?: string): string => {
  const map: Record<string, string> = {
    mastered: '精通', learning: '熟悉', familiar: '学习中',
    beginner: '入门', unknown: '未学习',
  }
  return level ? (map[level] || level) : '未知'
}

const domains = [
  { id: 'python', name: 'Python' }, { id: 'cpp', name: 'C/C++' },
  { id: 'java', name: 'Java' }, { id: 'algorithm', name: '算法' },
  { id: 'ml', name: '机器学习' }, { id: 'network', name: '计算机网络' },
  { id: 'database', name: '数据库' }, { id: 'system', name: '计算机系统' },
  { id: 'frontend', name: '前端开发' }, { id: 'go', name: 'Go语言' },
]

// ── API ──

async function loadList() {
  listLoading.value = true
  listError.value = ''
  try {
    const r = await api.get('/path/custom')
    const data = r.data
    // 兼容后端返回数组或包装对象
    graphs.value = Array.isArray(data) ? data : (data?.list || data?.data || [])
    if (graphs.value.length === 0) {
    }
  } catch (e: any) {
    const msg = e.response?.data?.detail || e.message || '网络错误'
    listError.value = '加载失败: ' + msg
  } finally {
    listLoading.value = false
  }
}

async function onSelect() {
  if (!selectedId.value) {
    graphData.value = null
    selectedNode.value = null
    graphLoading.value = false
    return
  }
  graphLoading.value = true
  try {
    const r = await api.get('/path/custom/' + selectedId.value)
    graphData.value = r.data
    saved.value = true

    // 确保每个节点都有 fallback 颜色和完整字段
    if (graphData.value?.nodes) {
      graphData.value.nodes.forEach((n: any) => {
        if (!n.color) n.color = phaseColorMap[n.phase] || '#94A3B8'
        if (n.p_known === undefined) n.p_known = 0
        if (!n.level) n.level = 'unknown'
      })
    }

    // 确保边数据存在
    if (!graphData.value.edges) graphData.value.edges = []

    selectedNode.value = null
    nodeIndex.value = null
    opMode.value = 'addNode'

    nextTick(renderChart)
  } catch (e: any) {
    ElMessage.error('加载图谱失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    graphLoading.value = false
  }
}

async function onCreate() {
  if (!title.value.trim()) return
  let ns: any[] = [], es: any[] = []

  // 从系统模板复制时带上颜色
  if (domain.value) {
    try {
      const r = await api.get('/path/graph/' + domain.value)
      ns = (r.data.nodes || []).map((n: any) => ({
        name: n.name || n.id,
        phase: n.phase || 'core',
        color: phaseColorMap[n.phase || 'core'] || '#2563EB',
      }))
      es = (r.data.edges || []).map((e: any) => ({
        source: e.source || '',
        target: e.target || '',
        relation: e.relation || 'prerequisite',
      }))
    } catch {}
  }

  try {
    const r = await api.post('/path/custom', {
      title: title.value.trim(),
      domain: domain.value || 'custom',
      nodes: ns,
      edges: es,
    })
    dlgCreate.value = false
    title.value = ''
    domain.value = ''
    await loadList()
    selectedId.value = r.data.id
    await onSelect()
  } catch (e: any) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  }
}

// ── 节点操作 ──

function addNode() {
  const name = nodeName.value.trim()
  if (!name || !graphData.value) return
  if (!graphData.value.nodes) graphData.value.nodes = []

  const phase = nodePhase.value
  graphData.value.nodes.push({
    name,
    phase,
    p_known: 0,
    color: phaseColorMap[phase] || '#94A3B8',
    level: 'unknown',
    notes: '',
  })

  nodeName.value = ''
  saved.value = false
  nextTick(renderChart)
}

function startEdit(index: number) {
  const n = graphData.value?.nodes?.[index]
  if (!n) return
  editingIndex.value = index
  editName.value = n.name
  editPhase.value = n.phase || 'core'
  opMode.value = 'editNode'
}

function saveEdit() {
  if (editingIndex.value === null || !graphData.value) return
  const name = editName.value.trim()
  if (!name) return

  const n = graphData.value.nodes[editingIndex.value]
  n.name = name
  n.phase = editPhase.value
  if (!n.p_known || n.p_known === 0) {
    n.color = phaseColorMap[editPhase.value] || '#94A3B8'
  }

  editingIndex.value = null
  editName.value = ''
  opMode.value = 'addNode'
  saved.value = false

  // 如果当前选中的是被编辑的节点，更新面板
  if (nodeIndex.value === editingIndex.value) {
    selectedNode.value = { ...n }
  }

  nextTick(renderChart)
}

function cancelEdit() {
  editingIndex.value = null
  editName.value = ''
  opMode.value = 'addNode'
}

async function removeNode(index: number) {
  if (!graphData.value?.nodes) return
  try {
    await ElMessageBox.confirm(`删除节点 "${graphData.value.nodes[index].name}"？`, '提示', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return  // user cancelled
  }

  const removedName = graphData.value.nodes[index].name
  graphData.value.nodes.splice(index, 1)

  // 同时删除关联的边
  if (graphData.value.edges) {
    graphData.value.edges = graphData.value.edges.filter(
      (e: any) => e.source !== removedName && e.target !== removedName
    )
  }

  // 如果删除的是当前选中节点，清空面板
  if (nodeIndex.value === index) {
    selectedNode.value = null
    nodeIndex.value = null
  } else if (nodeIndex.value !== null && nodeIndex.value > index) {
    nodeIndex.value--
  }

  saved.value = false
  nextTick(renderChart)
}

// ── 连线操作 ──

function addEdge() {
  if (edgeSource.value === null || edgeTarget.value === null || !graphData.value) return
  if (edgeSource.value === edgeTarget.value) return

  const nodes = graphData.value.nodes || []
  const srcName = nodes[edgeSource.value]?.name
  const tgtName = nodes[edgeTarget.value]?.name
  if (!srcName || !tgtName) return

  if (!graphData.value.edges) graphData.value.edges = []

  // 检查是否已存在相同边
  const exists = graphData.value.edges.some(
    (e: any) => e.source === srcName && e.target === tgtName
  )
  if (exists) {
    ElMessage.warning('该连线已存在')
    return
  }

  graphData.value.edges.push({
    source: srcName,
    target: tgtName,
    relation: 'prerequisite',
  })

  edgeSource.value = null
  edgeTarget.value = null
  saved.value = false
  nextTick(renderChart)
}

// ── 保存 ──

async function onSave() {
  if (!selectedId.value || !graphData.value) return
  saving.value = true
  try {
    const ns = (graphData.value.nodes || []).map((n: any) => ({
      name: n.name,
      phase: n.phase || 'core',
      notes: n.notes || '',
      color: n.color || '',
    }))
    const es = (graphData.value.edges || []).map((e: any) => ({
      source: e.source,
      target: e.target,
      relation: e.relation || 'prerequisite',
    }))
    await api.put('/path/custom/' + selectedId.value, { nodes: ns, edges: es })
    saved.value = true
    await loadList()
  } catch (e: any) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function onDelete() {
  if (!selectedId.value) return
  // Use ElMessageBox.confirm for async confirmation
  try {
    await ElMessageBox.confirm('确认删除此图谱？删除后不可恢复。', '提示', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return  // user cancelled
  }
  try {
    await api.delete('/path/custom/' + selectedId.value)
    selectedId.value = null
    graphData.value = null
    selectedNode.value = null
    await loadList()
  } catch (e: any) {
    ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

// ── ECharts 渲染（完全对标系统图谱 LearningPathView.vue）──

/** 节点大小计算 — 与系统图谱 dynamicNodeSize 一致 */
function nodeSize(pKnown: number): number {
  if (pKnown <= 0) return 22
  return Math.round(22 + pKnown * 18)
}

function renderChart() {
  if (!chartRef.value || !graphData.value?.nodes?.length) return
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }

  chartInstance = echarts.init(chartRef.value)
  const ns = graphData.value.nodes
  const es = graphData.value.edges || []

  // 构建节点数据（对标系统图谱 chartNodes 格式）
  const chartNodes = ns.map((n: any, i: number) => {
    const nodeColor = n.color || phaseColorMap[n.phase] || '#94A3B8'
    const pk = n.p_known || 0
    return {
      id: '' + i,
      name: n.name,
      symbolSize: nodeSize(pk),
      value: pk,
      itemStyle: {
        color: nodeColor,
        borderColor: pk > 0.35 ? 'rgba(255,255,255,0.6)' : 'transparent',
        borderWidth: pk > 0.35 ? 2 : 0,
        shadowBlur: pk > 0.85 ? 10 : (pk > 0.6 ? 6 : 0),
        shadowColor: pk > 0.85 ? 'rgba(16,185,129,0.3)' : (pk > 0.6 ? 'rgba(37,99,235,0.25)' : 'transparent'),
      },
      label: {
        show: true,
        fontSize: pk > 0 ? 12 : 11,
        fontWeight: pk > 0.6 ? 600 : 400,
        color: pk > 0 ? '#374151' : '#9CA3AF',
        position: 'bottom' as const,
      },
      category: n.phase === 'practice' ? 0 : n.phase === 'core' ? 1 : n.phase === 'advanced' ? 2 : 3,
    }
  })

  // 构建边数据（按名称匹配节点索引）
  const chartLinks: Array<{ source: string; target: string }> = []
  es.forEach((e: any) => {
    const si = ns.findIndex((n: any) => n.name === e.source)
    const ti = ns.findIndex((n: any) => n.name === e.target)
    if (si >= 0 && ti >= 0) {
      chartLinks.push({ source: '' + si, target: '' + ti })
    }
  })

  // 类别定义（4 阶段色系）
  const categories = [
    { name: '工程实战', itemStyle: { color: '#10B981' } },
    { name: '核心能力', itemStyle: { color: '#2563EB' } },
    { name: '进阶深入', itemStyle: { color: '#F59E0B' } },
    { name: '入门基础', itemStyle: { color: '#8B5CF6' } },
  ]

  const option: echarts.EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        if (params.dataType === 'node') {
          const d = params.data
          const pct = Math.round((d.value || 0) * 100)
          return `<b>${d.name}</b><br/>`
            + `阶段：${phaseLabel(ns[d.dataIndex]?.phase)}<br/>`
            + `等级：${statusLabel(ns[d.dataIndex]?.level)}<br/>`
            + `掌握概率：${pct}% (BKT p=${(d.value || 0).toFixed(3)})`
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
      roam: true,
      draggable: true,
      focusNodeAdjacency: true,
      force: {
        repulsion: 250,
        edgeLength: [100, 250],
        gravity: 0.1,
        friction: 0.6,
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3 },
        itemStyle: { shadowBlur: 20, shadowColor: 'rgba(59,130,246,0.4)' },
      },
      lineStyle: {
        color: '#94A3B8',
        curveness: 0.15,
        width: 1.5,
        opacity: 0.45,
      },
      label: { position: 'bottom' as const, formatter: '{b}' },
      edgeLabel: { show: false },
    }],
  }

  chartInstance.setOption(option)

  // 点击节点 → 右侧显示详情（对标系统图谱 selectNode）
  chartInstance.on('click', (params: any) => {
    if (params.dataType === 'node') {
      const idx = parseInt(params.data.id)
      const node = ns[idx]
      if (node) {
        selectedNode.value = { ...node }
        nodeIndex.value = idx
      }
    }
  })
}

function handleResize() {
  chartInstance?.resize()
}

/** 供父组件调用的刷新方法 */
async function refresh() {
  const currentToken = localStorage.getItem('token')
  if (currentToken) {
    token.value = currentToken
    await loadList()
    // 如果当前有选中图谱，重新加载
    if (selectedId.value) {
      await onSelect()
    }
  }
}

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  // 每次挂载时重新读取最新 token（防止登录状态变化后不刷新）
  await refresh()
})

// 暴露方法给父组件
defineExpose({ refresh, loadList })

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }
})
</script>

<style scoped>
.cg-layout {
  display: flex;
  gap: 16px;
  height: 100%;
  padding: 20px;
  overflow: hidden;
}
.cg-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
}
.cg-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.cg-toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.cg-toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.cg-error-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: #FEF2F2;
  border: 1px solid #FECACA;
  border-radius: 8px;
  color: #DC2626;
  font-size: 13px;
}
.cg-saved {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #10b981;
  font-weight: 500;
}
.cg-graph-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.cg-graph-title h3 {
  font-size: 16px;
  font-weight: 700;
  margin: 0;
}
.cg-sub {
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
}
.cg-op-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  padding: 10px 14px;
  background: var(--bg-secondary, #f8fafc);
  border-radius: 8px;
  border: 1px solid var(--border-color, #e2e8f0);
}
.cg-chart {
  flex: 1;
  min-height: 420px;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  background: #fafbfc;
}
.cg-empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

/* ═══ 右侧面板（对标系统图谱 kg-right） ═══ */
.cg-panel {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: #fff;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  padding: 16px;
  overflow-y: auto;
}
.cg-panel-hd {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary, #1e293b);
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
  margin-bottom: 4px;
}
.cg-panel-bd {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.detail-name {
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
}
.detail-status {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}
.detail-status.mastered { background: #D1FAE5; color: #059669; }
.detail-status.learning { background: #DBEAFE; color: #2563EB; }
.detail-status.familiar { background: #FEF3C7; color: #D97706; }
.detail-status.beginner { background: #EDE9FE; color: #7C3AED; }
.detail-status.unknown { background: #F1F5F9; color: #64748B; }
.detail-mastery {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.detail-mastery-bar {
  height: 8px;
  background: #E2E8F0;
  border-radius: 4px;
  overflow: hidden;
}
.detail-mastery-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}
.detail-mastery span {
  font-size: 11px;
  color: #64748B;
}
.detail-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.detail-subtitle {
  font-size: 11px;
  font-weight: 600;
  color: #64748B;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.phase-tag {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
}
.detail-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #E2E8F0;
}

/* ═══ Loading Spin ═══ */
.spin { animation: spin 1.2s linear infinite }
@keyframes spin { to { transform: rotate(360deg) } }

/* ═══════════ Responsive ═══════════ */
@media (max-width: 768px) {
  .cg-layout { flex-direction: column; padding: 12px; }
  .cg-main { flex: none; width: 100%; }
  .cg-toolbar { flex-direction: column; align-items: stretch; }
  .cg-toolbar-left { flex-wrap: wrap; }
  .cg-chart { min-height: 300px; touch-action: manipulation; }
  .cg-panel { width: 100%; flex-shrink: 1; }
  .cg-empty-state { min-height: 250px; }
}

@media (max-width: 480px) {
  .cg-layout { padding: 8px; gap: 8px; }
  .cg-toolbar { gap: 6px; }
  .cg-toolbar-left { gap: 4px; }
  .cg-toolbar-left .el-select { width: 180px !important; }
  .cg-chart { min-height: 240px; border-radius: 8px; }
  .cg-op-bar { padding: 8px 10px; gap: 4px; }
  .cg-panel { padding: 12px; gap: 8px; border-radius: 8px; }
  .detail-name { font-size: 14px; }
}
</style>
