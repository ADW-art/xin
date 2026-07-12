<template>
  <div class="agent-center">
    <!-- ═══ 主体内容区：拓扑图为核心 ═══ -->
    <main class="ac-body">
      <!-- 主拓扑图区域（占据核心） -->
      <section class="topology-main">
        <!-- 顶部工具条 -->
        <div class="topology-toolbar">
          <div class="toolbar-left">
            <el-icon :size="16" color="#2563EB"><Share /></el-icon>
            <strong>实时协作拓扑图</strong>
          </div>
          <div class="toolbar-center">
            <div class="toolbar-legend">
              <span class="legend-item"><span class="legend-marker marker-active"></span>活跃</span>
              <span class="legend-item"><span class="legend-marker marker-idle"></span>待命</span>
              <span class="legend-item"><span class="legend-line-mark"></span>数据流</span>
            </div>
          </div>
          <div class="toolbar-right">
            <!-- Agent 快速选择器（替代原左侧列表） -->
            <div class="agent-quick-select">
              <button
                v-for="agent in allAgents"
                :key="agent.name"
                class="quick-agent-btn"
                :class="{ active: agent.isActive, selected: selectedAgent === agent.name }"
                @click="selectAgent(agent.name)"
                :title="agent.label"
              >
                <el-icon :size="12"><component :is="agent.icon" /></el-icon>
                <span v-if="agent.calls > 0" class="btn-badge">{{ agent.calls }}</span>
              </button>
            </div>
          </div>
        </div>

        <!-- SVG画布区域 -->
        <div class="topology-canvas-wrapper">
          <!-- 会话统计浮动卡片（左上角） -->
          <div class="floating-stats">
            <div class="float-stat-title">
              <el-icon :size="13" color="#2563EB"><DataAnalysis /></el-icon>
              <span>本次会话</span>
            </div>
            <div class="float-stats-row">
              <div class="float-stat-item">
                <span class="float-num">{{ sessionStats.activeAgents }}</span>
                <span class="float-label">节点</span>
              </div>
              <div class="float-stat-divider"></div>
              <div class="float-stat-item">
                <span class="float-num">{{ sessionStats.totalRoutes }}</span>
                <span class="float-label">调度</span>
              </div>
              <div class="float-stat-divider"></div>
              <div class="float-stat-item">
                <span class="float-num">{{ sessionStats.totalTokens }}</span>
                <span class="float-label">消息</span>
              </div>
              <div class="float-stat-divider"></div>
              <div class="float-stat-item">
                <span class="float-num">{{ formatDuration(sessionStats.duration) }}</span>
                <span class="float-label">时长</span>
              </div>
            </div>
          </div>

          <svg :viewBox="`0 0 ${canvasWidth} ${canvasHeight}`" class="topology-svg">
            <defs>
              <filter id="nodeGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="3" result="blur"/>
                <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
              </filter>
              <radialGradient id="bgGradient" cx="50%" cy="30%" r="75%">
                <stop offset="0%" stop-color="#EFF6FF" stop-opacity="0.5"/>
                <stop offset="100%" stop-color="#F8FAFC" stop-opacity="0"/>
              </radialGradient>
              <marker id="arrowIdle" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#CBD5E1"/>
              </marker>
              <marker id="arrowActive" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#2563EB"/>
              </marker>
            </defs>

            <rect width="100%" height="100%" fill="url(#bgGradient)" rx="16"/>

            <!-- 连接边 -->
            <g class="edges-layer">
              <path
                v-for="edge in computedEdges"
                :key="edge.id"
                :d="edge.path"
                :stroke="edge.isActive ? '#2563EB' : '#CBD5E1'"
                :stroke-width="edge.isActive ? 2.5 : 1.5"
                :stroke-dasharray="edge.isActive ? 'none' : '6 4'"
                fill="none"
                :opacity="edge.isActive ? 0.85 : 0.6"
                :marker-end="edge.isActive ? `url(#arrowActive)` : `url(#arrowIdle)`"
                class="edge-line"
                :class="{ 'edge-live': edge.isActive }"
              />

              <!-- 数据流粒子 -->
              <circle
                v-for="particle in dataParticles"
                :key="'p-'+particle.id"
                :cx="particle.x" :cy="particle.y" r="3"
                fill="#2563EB"
                filter="url(#nodeGlow)"
                class="data-particle"
              />
            </g>

            <!-- Supervisor 主节点（顶部中心）-->
            <g class="node-group supervisor-group"
               :class="{ active: supervisorData.isActive, selected: selectedAgent === 'supervisor' }"
               @click="selectAgent('supervisor')">
              <circle v-if="supervisorData.isActive"
                      :cx="supervisorPos.x" :cy="supervisorPos.y" :r="48"
                      fill="none" stroke="#2563EB" stroke-width="1" opacity="0.25"
                      class="pulse-ring-anim"/>
              <circle :cx="supervisorPos.x" :cy="supervisorPos.y" :r="42"
                      :fill="supervisorData.isActive ? '#2563EB' : '#FFFFFF'"
                      :stroke="supervisorData.isActive ? '#1D4ED8' : '#CBD5E1'"
                      :stroke-width="supervisorData.isActive ? 2.5 : 1.8"
                      class="node-shape"/>
              <foreignObject :x="supervisorPos.x - 16" :y="supervisorPos.y - 16" width="32" height="32">
                <div class="node-icon-container" :style="{ color: supervisorData.isActive ? '#FFFFFF' : '#2563EB' }">
                  <el-icon :size="24"><Cpu /></el-icon>
                </div>
              </foreignObject>
              <text :x="supervisorPos.x" :y="supervisorPos.y + 56" text-anchor="middle"
                    class="node-text-label" :fill="supervisorData.isActive ? '#FFFFFF' : '#1E293B'" font-weight="700">
                {{ supervisorData.label }}
              </text>
              <text :x="supervisorPos.x" :y="supervisorPos.y + 70" text-anchor="middle"
                    class="node-role-text" fill="#64748B">
                {{ supervisorData.role }}
              </text>
              <g v-if="supervisorData.calls > 0"
                 :transform="`translate(${supervisorPos.x + 28}, ${supervisorPos.y - 28})`">
                <rect x="-14" y="-9" width="28" height="18" rx="9" fill="#2563EB"/>
                <text x="0" y="4" text-anchor="middle" fill="#fff" font-size="10" font-weight="700">{{ supervisorData.calls }}</text>
              </g>
            </g>

            <!-- Worker Agent 节点 -->
            <g v-for="agent in workerAgents"
               :key="agent.name"
               class="node-group worker-group"
               :class="{ active: agent.isActive, selected: selectedAgent === agent.name }"
               :transform="`translate(${agent.pos.x}, ${agent.pos.y})`"
               @click="selectAgent(agent.name)">
              <circle v-if="agent.isActive" cx="0" cy="0" r="34"
                      fill="none" stroke="#2563EB" stroke-width="1" opacity="0.2"
                      class="pulse-ring-anim"/>
              <rect x="-38" y="-24" width="76" height="48" rx="11"
                    :fill="agent.isActive ? '#2563EB' : '#FFFFFF'"
                    :stroke="agent.isActive ? '#1D4ED8' : '#CBD5E1'"
                    :stroke-width="agent.isActive ? 2 : 1.6"
                    class="node-shape"/>
              <foreignObject x="-14" y="-14" width="28" height="28">
                <div class="node-icon-container" :style="{ color: agent.isActive ? '#FFFFFF' : '#2563EB' }">
                  <el-icon :size="20"><component :is="agent.icon" /></el-icon>
                </div>
              </foreignObject>
              <text x="0" y="36" text-anchor="middle"
                    class="node-text-label" :fill="agent.isActive ? '#FFFFFF' : '#1E293B'" font-weight="700" font-size="11">
                {{ agent.label }}
              </text>
              <text x="0" y="48" text-anchor="middle" class="node-role-text" fill="#64748B" font-size="9">
                {{ agent.role }}
              </text>
              <g v-if="agent.calls > 0" transform="translate(26, -16)">
                <rect x="-12" y="-8" width="24" height="16" rx="8" fill="#2563EB"/>
                <text x="0" y="4" text-anchor="middle" fill="#fff" font-size="9" font-weight="700">{{ agent.calls }}</text>
              </g>
            </g>

            <!-- 用户输入节点 -->
            <g transform="translate(70, 420)">
              <circle cx="0" cy="0" r="26" fill="#EFF6FF" stroke="#93C5FD" stroke-width="1.8"/>
              <foreignObject x="-14" y="-14" width="28" height="28">
                <div class="node-icon-container" style="color:#1D4ED8">
                  <el-icon :size="18"><User /></el-icon>
                </div>
              </foreignObject>
              <text x="0" y="38" text-anchor="middle" font-size="11" fill="#475569" font-weight="500">用户输入</text>
            </g>

            <!-- 输出节点 -->
            <g transform="translate(750, 420)">
              <circle cx="0" cy="0" r="26" fill="#EFF6FF" stroke="#93C5FD" stroke-width="1.8"/>
              <foreignObject x="-14" y="-14" width="28" height="28">
                <div class="node-icon-container" style="color:#1D4ED8">
                  <el-icon :size="18"><ChatDotRound /></el-icon>
                </div>
              </foreignObject>
              <text x="0" y="38" text-anchor="middle" font-size="11" fill="#475569" font-weight="500">响应输出</text>
            </g>
          </svg>
        </div>

        <!-- 底部：调用轨迹 -->
        <div class="trace-panel">
          <div class="trace-head">
            <div class="trace-title-row">
              <el-icon :size="13" color="#2563EB"><List /></el-icon>
              <span>实时调用轨迹</span>
            </div>
            <span class="trace-count-badge">最近 {{ Math.min(traces.length, 20) }} 条</span>
          </div>
          <div class="trace-scroll">
            <div v-if="traces.length === 0" class="trace-empty-state">
              <el-icon :size="32" color="#CBD5E1"><Connection /></el-icon>
              <p>启动对话后，协作链路将在此呈现</p>
              <router-link to="/chat" class="trace-action-link">前往对话 →</router-link>
            </div>
            <TransitionGroup name="trace-animate" tag="div" class="trace-list">
              <div v-for="trace in displayTraces" :key="trace.id"
                   class="trace-entry" :class="{ fresh: trace.isNew }">
                <span class="trace-time">{{ trace.timeLabel }}</span>
                <span class="trace-source">
                  <el-icon :size="11"><component :is="trace.fromIcon" /></el-icon>
                  {{ trace.fromName }}
                </span>
                <el-icon :size="10" color="#CBD5E1"><Right /></el-icon>
                <span class="trace-target">
                  <el-icon :size="11"><component :is="trace.toIcon" /></el-icon>
                  {{ trace.toName }}
                </span>
                <span class="trace-meta">
                  <span>{{ formatDuration(trace.durationMs) }}</span>
                  <span v-if="trace.tokens > 0" class="token-tag">{{ trace.tokens }}T</span>
                </span>
              </div>
            </TransitionGroup>
          </div>
        </div>
      </section>

      <!-- 右侧：选中详情（条件显示） -->
      <aside class="sidebar-right" v-if="selectedAgentDetail">
        <div class="detail-top-bar">
          <div class="detail-avatar-lg">
            <el-icon :size="18"><component :is="selectedAgentDetail.icon" /></el-icon>
          </div>
          <div class="detail-name-block">
            <span class="detail-agent-name">{{ selectedAgentDetail.label }}</span>
            <span class="detail-agent-type">{{ selectedAgentDetail.category === 'supervisor' ? '调度中枢' : '执行节点' }}</span>
          </div>
        </div>

        <div class="detail-content">
          <div class="detail-section">
            <h4 class="detail-section-title">功能描述</h4>
            <p class="detail-section-text">{{ selectedAgentDetail.description }}</p>
          </div>

          <div class="detail-section">
            <h4 class="detail-section-title">运行指标</h4>
            <div class="metrics-grid">
              <div class="metric-cell">
                <span class="metric-value">{{ selectedAgentDetail.calls }}</span>
                <span class="metric-label">调用次数</span>
              </div>
              <div class="metric-cell">
                <span class="metric-value">{{ formatTokens(selectedAgentDetail.tokens) }}</span>
                <span class="metric-label">Token用量</span>
              </div>
              <div class="metric-cell">
                <span class="metric-value">{{ selectedAgentDetail.avgMs > 0 ? formatDuration(selectedAgentDetail.avgMs) : '-' }}</span>
                <span class="metric-label">平均耗时</span>
              </div>
              <div class="metric-cell">
                <span class="metric-value">{{ selectedAgentDetail.lastPreview ? '有' : '-' }}</span>
                <span class="metric-label">最近输出</span>
              </div>
            </div>
          </div>

          <div class="detail-section" v-if="selectedAgentDetail.keywords?.length">
            <h4 class="detail-section-title">触发关键词</h4>
            <div class="keywords-wrap">
              <span
                v-for="kw in selectedAgentDetail.keywords.slice(0, 8)"
                :key="kw"
                class="keyword-pill clickable"
                @click="quickChat(selectedAgentDetail.name, kw)"
                :title="'点击快速调用 ' + selectedAgentDetail.displayName"
              >{{ kw }}</span>
            </div>
          </div>
        </div>

        <button class="close-detail-btn" @click="selectedAgent = null">
          <el-icon :size="12"><Close /></el-icon>
        </button>
      </aside>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'
import api from '@/api/index'

const chatStore = useChatStore()
const userStore = useUserStore()

// ── Canvas 尺寸（大屏展示）──
const canvasWidth = 820
const canvasHeight = 480

// ── 状态变量 ──
// (loading ref removed — unused)
const isSystemActive = ref(false)
const selectedAgent = ref<string | null>(null)
const traces = ref<any[]>([])
const sessionStartTime = ref(Date.now())
let traceCounter = 0

// 会话统计数据
const sessionStats = reactive({
  activeAgents: 0,
  totalRoutes: 0,
  totalTokens: 0,
  duration: 0,
})

// ── Agent 接口定义 ──
interface AgentInfo {
  name: string
  label: string
  displayName?: string
  role: string
  description: string
  icon: string
  category: string
  calls: number
  tokens: number
  totalMs: number
  avgMs: number
  isActive: boolean
  lastPreview: string
  keywords?: string[]
  pos: { x: number; y: number }
}

const agentsRegistry = reactive<Record<string, AgentInfo>>({})

// 动态计算 Worker 节点椭圆弧布局
function computeArcLayout(count: number): { x: number; y: number }[] {
  const cx = canvasWidth / 2
  const cy = canvasHeight * 0.52
  const rx = canvasWidth * 0.36
  const ry = canvasHeight * 0.30
  const positions: { x: number; y: number }[] = []
  for (let i = 0; i < count; i++) {
    const angle = (Math.PI * 2 * i) / count - Math.PI / 2
    positions.push({
      x: Math.round(cx + rx * Math.cos(angle)),
      y: Math.round(cy + ry * Math.sin(angle)),
    })
  }
  return positions
}

// 默认 Agent 配置（/api/agent-trace/manifest 不可用时的 fallback）
const defaultAgentsConfig: Omit<AgentInfo, 'calls' | 'tokens' | 'totalMs' | 'avgMs' | 'isActive' | 'lastPreview' | 'pos'>[] = [
  { name: 'supervisor', label: 'Supervisor', role: '意图调度',
    description: '接收用户输入，分析意图并智能路由到最合适的专家 Agent 执行任务。负责协调多 Agent 协作流程。',
    icon: 'Cpu', category: 'supervisor',
    keywords: ['意图识别', '任务路由', '流程协调', '结果汇总'],
  },
  { name: 'profile_agent', label: 'Profile', role: '学习者画像',
    description: '采集和分析学习者的认知特征、学习风格、知识基础等多维画像信息。',
    icon: 'User', category: 'worker',
    keywords: ['画像采集', '学习风格', '认知分析', '个性化'],
  },
  { name: 'resource_agent', label: 'Resource', role: '资源生成',
    description: '根据学习需求自动生成教材、思维导图、代码案例等多模态学习资源。',
    icon: 'FolderOpened', category: 'worker',
    keywords: ['资源生成', '教材制作', '思维导图', '案例编写'],
  },
  { name: 'question_agent', label: 'Question', role: '自适应出题',
    description: '基于知识图谱动态生成难度适配的练习题，支持错题追踪与举一反三。',
    icon: 'EditPen', category: 'worker',
    keywords: ['智能出题', '难度自适应', '错题追踪', '练习生成'],
  },
  { name: 'evaluation_agent', label: 'Evaluation', role: '学习评估',
    description: '综合评估学习效果，分析掌握程度和薄弱环节，提供改进建议。',
    icon: 'TrendCharts', category: 'worker',
    keywords: ['效果评估', '能力分析', '薄弱诊断', '改进建议'],
  },
  { name: 'path_agent', label: 'Path', role: '路径规划',
    description: '基于知识图谱构建个性化学习路径，规划最优学习顺序和里程碑。',
    icon: 'Guide', category: 'worker',
    keywords: ['路径规划', '学习计划', '进度管理', '里程碑'],
  },
  { name: 'chat_agent', label: 'Chat', role: '对话助手',
    description: '通用对话交互 Agent，处理日常问答、概念解释和引导式学习对话。',
    icon: 'ChatDotRound', category: 'worker',
    keywords: ['对话问答', '概念解释', '引导学习', '日常交互'],
  },
]

// 使用动态布局填充注册表
const workerDefs = defaultAgentsConfig.filter(c => c.category === 'worker')
const arcPositions = computeArcLayout(workerDefs.length)
let _wi = 0
defaultAgentsConfig.forEach(cfg => {
  const pos = cfg.category === 'supervisor'
    ? { x: canvasWidth / 2, y: 60 }
    : arcPositions[_wi++]
  agentsRegistry[cfg.name] = { ...cfg, pos, calls: 0, tokens: 0, totalMs: 0, avgMs: 0, isActive: false, lastPreview: '' }
})

// ── 计算属性 ──
const supervisorData = computed(() => agentsRegistry['supervisor'])
const supervisorPos = computed(() => ({ x: canvasWidth / 2, y: 60 }))
const workerAgents = computed(() => Object.values(agentsRegistry).filter(a => a.category === 'worker'))
const allAgents = computed(() => Object.values(agentsRegistry))
const selectedAgentDetail = computed(() => selectedAgent.value ? agentsRegistry[selectedAgent.value] : null)
// (deprecated computed wrappers removed — template reads sessionStats directly)

// 边路径计算
const computedEdges = computed(() => {
  const edges: any[] = []
  const sp = supervisorPos.value
  workerAgents.value.forEach(agent => {
    const midY = (sp.y + agent.pos.y) / 2 + 10
    const path = `M ${sp.x} ${sp.y + 38} Q ${sp.x} ${midY} ${(sp.x + agent.pos.x) / 2} ${midY} T ${agent.pos.x} ${agent.pos.y - 22}`
    edges.push({ id: `edge-sp-${agent.name}`, path, isActive: agent.isActive })
  })
  return edges
})

// 数据流粒子
interface DataParticle {
  id: number; x: number; y: number; targetName: string; progress: number; speed: number }
const dataParticles = ref<DataParticle[]>([])
let particleIdSeq = 0
let animationFrameId: number | null = null

function emitParticle(targetName: string) {
  const target = agentsRegistry[targetName]
  if (!target) return
  const sp = supervisorPos.value
  particleIdSeq++
  dataParticles.value.push({
    id: particleIdSeq,
    x: sp.x, y: sp.y + 38, targetName,
    progress: 0, speed: 0.012 + Math.random() * 0.008,
  })
}

function runParticleAnimation() {
  dataParticles.value = dataParticles.value.filter(p => {
    p.progress += p.speed
    if (p.progress >= 1) return false
    const t = p.progress, mt = 1 - t
    const sp = supervisorPos.value
    const agent = agentsRegistry[p.targetName]
    if (!agent) return false
    const midY = (sp.y + agent.pos.y) / 2 + 10
    const endX = (sp.x + agent.pos.x) / 2
    p.x = mt * mt * sp.x + 2 * mt * t * sp.x + t * t * endX
    p.y = mt * mt * (sp.y + 38) + 2 * mt * t * midY + t * t * (agent.pos.y - 22)
    return true
  })
  animationFrameId = requestAnimationFrame(runParticleAnimation)
}

// 显示轨迹
const displayTraces = computed(() =>
  traces.value.slice(-20).reverse().map(t => ({
    ...t,
    timeLabel: new Date(t.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    fromName: agentsRegistry[t.from]?.label || t.from,
    toName: agentsRegistry[t.to]?.label || t.to,
    fromIcon: agentsRegistry[t.from]?.icon || 'QuestionFilled',
    toIcon: agentsRegistry[t.to]?.icon || 'QuestionFilled',
  }))
)

// ── 方法函数 ──
function selectAgent(name: string) {
  selectedAgent.value = selectedAgent.value === name ? null : name
}

function resetSession() {
  traces.value = []
  Object.keys(sessionStats).forEach(key => { ;(sessionStats as any)[key] = 0 })
  Object.values(agentsRegistry).forEach(a => { a.calls = 0; a.tokens = 0; a.totalMs = 0; a.avgMs = 0; a.isActive = false; a.lastPreview = '' })
  sessionStartTime.value = Date.now()
}

function formatTokens(tokens: number): string {
  if (tokens <= 0) return '—'
  return tokens >= 1000 ? (tokens / 1000).toFixed(1) + 'K' : String(tokens)
}
function formatDuration(ms: number): string {
  return ms >= 1000 ? (ms / 1000).toFixed(1) + 's' : ms + 'ms'
}

// ── 监听 ChatStore 实时数据 ──
let currentActiveAgent = 'supervisor'
let lastTraceTimestamp = Date.now()

watch(() => chatStore.isStreaming, (streaming, prev) => {
  isSystemActive.value = streaming
  if (streaming && !animationFrameId) animationFrameId = requestAnimationFrame(runParticleAnimation)
  // 对话结束 → 拉取真实 Agent 调用链（含后端统计的真实 token / 耗时）覆盖 SSE 估算轨迹
  if (!streaming && prev) {
    setTimeout(() => { loadLatestTrace() }, 600)
  }
})

watch(
  () => [...chatStore.messages],
  () => {
    const messages = chatStore.messages
    if (!messages.length) return
    const latestMsg = messages[messages.length - 1]

    if (latestMsg.agentSwitch) {
      const { from, to } = latestMsg.agentSwitch
      currentActiveAgent = to
      Object.values(agentsRegistry).forEach(a => { a.isActive = false })
      if (agentsRegistry[to]) agentsRegistry[to].isActive = true
      if (agentsRegistry['supervisor']) agentsRegistry['supervisor'].isActive = true

      const now = Date.now()
      const elapsed = now - lastTraceTimestamp
      lastTraceTimestamp = now
      // 真实 Token 数据可通过 /api/agent-trace/latest 查询，SSE 事件不含 token 统计
      const estimatedTokens = 0

      traceCounter++
      traces.value.push({ id: traceCounter, from, to, durationMs: elapsed, tokens: estimatedTokens, timestamp: now, isNew: true })

      if (traces.value.length > 80) traces.value.shift()

      const targetAgent = agentsRegistry[to]
      if (targetAgent) {
        targetAgent.calls++
        targetAgent.totalMs += elapsed
        targetAgent.avgMs = targetAgent.totalMs / targetAgent.calls
        if (latestMsg.content) targetAgent.lastPreview = latestMsg.content.slice(0, 80)
      }

      const sup = agentsRegistry['supervisor']
      if (sup) sup.calls++

      const participatingAgents = new Set(traces.value.map((t: any) => t.to))
      sessionStats.activeAgents = participatingAgents.size
      sessionStats.totalRoutes = traces.value.length
      sessionStats.totalTokens = chatStore.messages.length
      sessionStats.duration = now - sessionStartTime.value

      if (to !== 'supervisor') emitParticle(to)

      setTimeout(() => { traces.value.forEach(t => { t.isNew = false }) }, 3000)
    }

    if (latestMsg.agent && latestMsg.agent !== currentActiveAgent) {
      currentActiveAgent = latestMsg.agent
      if (agentsRegistry[latestMsg.agent]) agentsRegistry[latestMsg.agent].isActive = true
    }
  },
  { deep: true }
)

// ── 加载历史数据 ──
const router = useRouter()

// Keyword → prompt mapping: 关键词触发的对话提示词（对标官网Agent功能）
const KEYWORD_PROMPTS: Record<string, string> = {
  '意图识别': '你好，我想了解一下学习系统',
  '任务路由': '帮我规划Python学习路线',
  '流程协调': '我想系统学习Python，从基础开始',
  '结果汇总': '给我做一份学习评估报告',
  '画像采集': '我想完善我的学习画像',
  '学习风格': '我更喜欢动手写代码来学习',
  '认知分析': '分析一下我的学习情况',
  '个性化': '根据我的画像推荐学习内容',
  '资源生成': '生成Python装饰器的知识文档',
  '教材制作': '帮我写Python入门教程',
  '思维导图': '生成Python基础知识的思维导图',
  '案例编写': '写一个Python文件读写的代码示例',
  '智能出题': '出3道Python算法练习题',
  '难度自适应': '根据我的水平出Python题目',
  '错题追踪': '给我出几道之前做错的类似题目',
  '练习生成': '给我出几道Python基础练习题',
  '效果评估': '给我做一份Python学习评估报告',
  '能力分析': '评估我当前的Python掌握情况',
  '薄弱诊断': '分析一下我的Python薄弱环节',
  '改进建议': '给我一些Python学习的改进建议',
  '路径规划': '帮我规划Python学习路线',
  '学习计划': '制定一个30天Python学习计划',
  '进度管理': '帮我检查当前的学习进度',
  '里程碑': '帮我设定Python学习的阶段目标',
  '对话问答': 'Python装饰器是什么',
  '概念解释': '解释一下Python的闭包概念',
  '引导学习': '我想学Python，从哪里开始',
  '日常交互': '你好，今天适合学什么',
}

function quickChat(agentName: string, keyword: string) {
  const prompt = KEYWORD_PROMPTS[keyword] || keyword
  // 导航到对话页并通过 query 参数传递预设提示词
  router.push({ path: '/chat', query: { prompt, agent: agentName } })
}

// ── 真实 Agent 调用链追踪 (GET /api/agent-trace/latest) ──
// 后端约定 thread_id = `user-{user_id}`（见 chat.py），用真实调用链替换 SSE 估算轨迹
async function loadLatestTrace() {
  let uid = userStore.userInfo?.id
  if (!uid) {
    try { await userStore.fetchUserInfo() } catch { /* 未登录则跳过 */ }
    uid = userStore.userInfo?.id
  }
  if (!uid) return
  try {
    const { data } = await api.get('/agent-trace/latest', {
      params: { thread_id: `user-${uid}` },
    })
    applyLatestTrace(data)
  } catch (error) {
    console.warn('AgentCenter: 获取最新调用链追踪失败', error)
  }
}

// 将后端 TraceResponse 渲染到拓扑图：调用轨迹 + 各 Agent 真实指标
function applyLatestTrace(data: any) {
  const chain: any[] = data?.call_chain || []
  const edges: any[] = data?.edges || []
  // 无真实追踪数据（新用户 / 服务重启后内存 checkpoint 丢失）→ 保留历史派生状态
  if (!chain.length) return

  // 1) 用真实节点指标更新各 Agent（token / 平均耗时 / 输出预览 均来自后端真实统计）
  const nodeByAgent: Record<string, any> = {}
  chain.forEach((n: any) => {
    nodeByAgent[n.agent] = n
    const a = agentsRegistry[n.agent]
    if (!a) return
    a.tokens = (n.input_tokens || 0) + (n.output_tokens || 0)
    a.avgMs = Math.round(n.duration_ms || 0)
    a.totalMs = a.avgMs
    if (n.output_preview) a.lastPreview = n.output_preview
    if (n.display_name) a.label = n.display_name
  })

  // 2) 用真实 edges 重建调用轨迹（替换 SSE 估算 tokens=0 的占位轨迹）
  const baseTs = Date.now()
  traces.value = edges.map((e: any, i: number) => {
    const tNode = nodeByAgent[e.target]
    return {
      id: i + 1,
      from: e.source,
      to: e.target,
      durationMs: Math.round(tNode?.duration_ms || 0),
      tokens: tNode ? (tNode.input_tokens || 0) + (tNode.output_tokens || 0) : 0,
      timestamp: baseTs + i,
      isNew: false,
    }
  })
  traceCounter = traces.value.length  // 后续 SSE 轨迹从此处继续递增 id，避免冲突

  // 高亮本次调用链中出现的 Agent 节点
  const usedAgents: string[] = data?.agents_used || chain.map((n: any) => n.agent)
  Object.values(agentsRegistry).forEach(a => { a.isActive = false })
  usedAgents.forEach((name: string) => { if (agentsRegistry[name]) agentsRegistry[name].isActive = true })
  if (agentsRegistry['supervisor']) agentsRegistry['supervisor'].isActive = true
}

onMounted(async () => {
  try {
    const [manifestResult, historyResult] = await Promise.all([
      api.get('/agent-trace/manifest').catch(() => ({ data: [] })),
      api.get('/chat/history', { params: { limit: 50 } }).catch(() => ({ data: [] })),
    ])

    const manifestList: any[] = manifestResult.data || []
    if (manifestList.length > 0) {
      // 以 manifest API 数据为权威来源，更新/新建所有 Agent 定义
      manifestList.forEach((item: any) => {
        if (agentsRegistry[item.name]) {
          // 更新已有 Agent 的元数据
          if (item.displayName) agentsRegistry[item.name].label = item.displayName
          if (item.description) agentsRegistry[item.name].description = item.description
          if (item.icon) agentsRegistry[item.name].icon = item.icon
          if (item.keywords) agentsRegistry[item.name].keywords = item.keywords
        } else {
          // 新 Agent（不在 fallback 中）
          agentsRegistry[item.name] = {
            name: item.name, label: item.displayName || item.name,
            role: item.description?.slice(0, 10) || '', description: item.description || '',
            icon: item.icon || 'QuestionFilled', category: item.category || 'worker',
            calls: 0, tokens: 0, totalMs: 0, avgMs: 0, isActive: false, lastPreview: '',
            keywords: item.keywords, pos: { x: 0, y: 0 },  // 下面统一重新计算位置
          }
        }
      })
      // 用动态布局重新计算所有 worker 位置
      const positions = computeArcLayout(
        Object.values(agentsRegistry).filter(a => a.category === 'worker').length
      )
      let pi = 0
      Object.values(agentsRegistry).forEach(a => {
        if (a.category === 'supervisor') {
          a.pos = { x: canvasWidth / 2, y: 70 }
        } else if (a.category === 'worker') {
          a.pos = positions[pi++] || { x: canvasWidth / 2, y: canvasHeight * 0.6 }
        }
      })
    }

    const historyList: any[] = historyResult.data || []
    const agentCallCounts: Record<string, number> = {}

    historyList.forEach((record: any) => {
      if (record.agent_type) {
        agentCallCounts[record.agent_type] = (agentCallCounts[record.agent_type] || 0) + 1
      }
    })

    Object.entries(agentCallCounts).forEach(([name, count]) => {
      if (agentsRegistry[name]) {
        agentsRegistry[name].calls = count
      }
    })

    sessionStats.totalRoutes = historyList.filter((h: any) => h.agent_type).length
    sessionStats.activeAgents = Object.keys(agentCallCounts).length
    sessionStats.totalTokens = historyList.length  // 历史消息总数

    // 拉取最近一次真实 Agent 调用链 → 用真实 token/耗时/轨迹覆盖历史估算
    await loadLatestTrace()

  } catch (error) {
    console.warn('AgentCenter: 历史数据加载异常', error)
  }
})

onUnmounted(() => {
  if (animationFrameId) cancelAnimationFrame(animationFrameId)
})
</script>

<style scoped>
/* ═══ 全局容器 ═══ */
.agent-center {
  height: 100dvh;
  display: flex;
  flex-direction: column;
  background: #F5F7FA;
  overflow: hidden;
  min-height: 0;
}

/* ═══ Main Body（拓扑图为核心） ═══ */
.ac-body {
  flex: 1; display: flex; overflow: hidden; gap: 0;
  min-height: 0; min-width: 0;
}

/* ═══ 拓扑图主区域 ═══ */
.topology-main {
  flex: 1; display: flex; flex-direction: column;
  min-width: 0; min-height: 0; overflow: hidden;
  background: #F8FAFC;
}

/* 工具条：三段式布局（优化：更紧凑） */
.topology-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 18px; background: #fff;
  flex-shrink: 0;
  gap: 14px;
}
.toolbar-left { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #334155; flex-shrink: 0; }
.toolbar-center { flex: 1; display: flex; justify-content: center; }
.toolbar-right { flex-shrink: 0; }

.toolbar-legend { display: flex; gap: 16px; }
.legend-item { display: flex; align-items: center; gap: 4px; font-size: 11px; color: #64748B; }
.legend-marker { width: 8px; height: 8px; border-radius: 50%; }
.marker-active { background: #2563EB; }
.marker-idle { background: #CBD5E1; }
.legend-line-mark {
  width: 18px; height: 2px; background: #93C5FD; border-radius: 1px; position: relative;
}
.legend-line-mark::after {
  content: ''; position: absolute; right: -2px; top: -3px;
  border: 4px solid transparent; border-left-color: #93C5FD;
}

/* Agent 快速选择器（替代原左侧列表） */
.agent-quick-select {
  display: flex; gap: 4px; background: #F8FAFC;
  padding: 4px; border-radius: 10px; border: 1px solid #E8ECF1;
}
.quick-agent-btn {
  position: relative; width: 32px; height: 32px; border: none;
  border-radius: 8px; background: #fff; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: #94A3B8; transition: all 0.2s; border: 1.5px solid transparent;
}
.quick-agent-btn:hover { background: #EFF6FF; color: #2563EB; border-color: #BFDBFE; }
.quick-agent-btn.active { background: #10B981; color: #fff; border-color: #10B981; box-shadow: 0 2px 8px rgba(16,185,129,.25); }
.quick-agent-btn.selected { border-color: #F59E0B; }
.btn-badge {
  position: absolute; top: -4px; right: -4px;
  min-width: 15px; height: 15px; padding: 0 4px;
  background: #F59E0B; color: #fff; border-radius: 8px;
  font-size: 9px; font-weight: 700; display: flex; align-items: center; justify-content: center;
}

/* ═══ 浮动统计卡片（左上角） ═══ */
.floating-stats {
  position: absolute; top: 12px; left: 12px; z-index: 10;
  background: rgba(255,255,255,.96); backdrop-filter: blur(12px);
  border: 1.5px solid #CBD5E1; border-radius: 12px;
  padding: 12px 16px; min-width: 240px;
  box-shadow: 0 4px 20px rgba(0,0,0,.08);
}
.float-stat-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; font-weight: 600; color:#334155;
  margin-bottom: 8px; padding-bottom: 6px;
  border-bottom: 1px dashed #E2E8F0;
}
.float-stats-row { display: flex; align-items: center; gap: 8px; }
.float-stat-item { text-align: center; flex: 1; }
.float-num { display: block; font-size: 18px; font-weight: 800; color: #1E293B; line-height: 1.2; }
.float-label { display: block; font-size: 9px; color: #64748B; margin-top: 3px; }
.float-stat-divider { width: 1px; height: 28px; background: #E8ECF1; }

/* ═══ Canvas 区域（优化：更大空间） ═══ */
.topology-canvas-wrapper {
  flex: 1; min-height: 0;
  display: flex; align-items: center; justify-content: center;
  padding: 6px 10px; overflow: hidden;
  position: relative;
}
.topology-svg {
  width: 100%; height: 100%;
  max-width: 820px; max-height: 480px;
  filter: drop-shadow(0 2px 6px rgba(0,0,0,.03));
}

/* SVG 节点样式 */
.node-group { cursor: pointer; }
.node-shape { transition: all 0.3s ease; }
.node-group:hover .node-shape { filter: brightness(0.97); }
.node-group.active .node-shape { filter: drop-shadow(0 0 10px rgba(37,99,235,.35)); }
.node-group.selected .node-shape { stroke-width: 2.5; }
.node-icon-container {
  display: flex; align-items: center; justify-content: center;
  width: 100%; height: 100%;
}
.node-text-label { font-size: 12px; font-weight: 700; letter-spacing: 0.2px; }
.node-role-text { font-size: 9px; font-weight: 500; }

.pulse-ring-anim { transform-origin: center; animation: ringPulseAnim 2s infinite; }
@keyframes ringPulseAnim {
  0% { transform: scale(1); opacity: 0.25; }
  100% { transform: scale(1.4); opacity: 0; }
}
.edge-line { transition: all 0.3s ease; }
.edge-live { animation: edgeFlash 1.5s ease-out; }
@keyframes edgeFlash { 0% { opacity: 1; } 100% { opacity: 0.55; } }
.data-particle { pointer-events: none; }

/* ═══ Trace Panel（优化：更紧凑） ═══ */
.trace-panel {
  flex-shrink: 0; background: #F0F4FF;
  height: 110px; min-height: 70px; max-height: 140px;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.trace-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 7px 20px; flex-shrink: 0;
  background: rgba(255,255,255,.6);
}
.trace-title-row { display: flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 600; color: #10B981; }
.trace-count-badge { font-size: 10px; color: #64748B; background: #ECFDF5; padding: 2px 10px; border-radius: 10px; font-weight: 500; }

.trace-scroll {
  flex: 1; overflow-y: auto; overflow-x: hidden;
  padding: 4px 20px 8px;
}
.trace-empty-state {
  display: flex; flex-direction: column; align-items: center;
  padding: 18px 0; gap: 8px; color: #94A3B8;
}
.trace-empty-state p { font-size: 12px; margin: 0; }
.trace-action-link { color: #2563EB; text-decoration: none; font-size: 11px; font-weight: 500; }
.trace-action-link:hover { text-decoration: underline; }

.trace-list { display: flex; flex-direction: column; }
.trace-entry {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 10px; border-bottom: 1px solid #F0F4FF;
  font-size: 11px; transition: all 0.2s; border-radius: 6px; margin: 1px 0;
}
.trace-entry:hover { background: #EFF6FF; }
.trace-entry.fresh { background: #D1FAE5; border-left: 3px solid #10B981; }
.trace-time { font-size: 9px; color: #94A3B8; width: 56px; flex-shrink: 0; font-variant-numeric: tabular-nums; }
.trace-source, .trace-target {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 11px; font-weight: 600; white-space: nowrap; color: #374151;
}
.trace-meta { margin-left: auto; display: flex; gap: 6px; font-size: 9px; color: #94A3B8; flex-shrink: 0; }
.token-tag { color: #8B5CF6; font-weight: 600; background: #F5F3FF; padding: 1px 5px; border-radius: 3px; }

.trace-animate-enter-active { transition: all 0.3s ease-out; }
.trace-animate-enter-from { opacity: 0; transform: translateX(-10px); }

/* ═══ Right Sidebar ═══ */
.sidebar-right {
  width: 260px; flex-shrink: 0;
  background: #F8FAFC;
  border-left: 1px solid #E8ECF1;
  overflow-y: auto; overflow-x: hidden;
  position: relative; animation: slideInRight 0.25s ease-out;
  min-height: 0;
  box-shadow: -4px 0 20px rgba(139,92,246,0.06);
}
@keyframes slideInRight {
  from { opacity: 0; transform: translateX(12px); }
  to { opacity: 1; transform: translateX(0); }
}

.detail-top-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 16px; border-bottom: 1px solid #E8ECF1;
  background: #F5F3FF;
}
.detail-avatar-lg {
  width: 42px; height: 42px; border-radius: 12px;
  background: #8B5CF6;
  display: flex; align-items: center; justify-content: center;
  color: #fff; flex-shrink: 0; box-shadow: 0 2px 8px rgba(139,92,246,.2);
}
.detail-name-block { flex: 1; min-width: 0; }
.detail-agent-name { display: block; font-size: 14px; font-weight: 700; color: #1E293B; }
.detail-agent-type { display: block; font-size: 10px; color: #64748B; margin-top: 3px; font-weight: 500; }

.detail-content { padding: 14px 16px; display: flex; flex-direction: column; gap: 14px; }
.detail-section {}
.detail-section-title {
  font-size: 10px; font-weight: 600; color: #8B5CF6;
  margin: 0 0 6px 0; text-transform: uppercase; letter-spacing: 0.6px;
}
.detail-section-text { font-size: 11px; color: #475569; line-height: 1.7; margin: 0; }

.metrics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.metric-cell {
  background: #EFF6FF; border: 1px solid #E2E8F0;
  border-radius: 10px; padding: 10px 8px; text-align: center;
  transition: all 0.2s;
}
.metric-cell:hover { border-color: #BFDBFE; transform: translateY(-1px); }
.metric-value { display: block; font-size: 15px; font-weight: 700; color: #1E293B; }
.metric-label { display: block; font-size: 9px; color: #94A3B8; margin-top: 3px; }

.keywords-wrap { display: flex; flex-wrap: wrap; gap: 5px; }
.keyword-pill {
  padding: 3px 10px; background: #EEF2FF;
  color: #4338CA; border-radius: 5px; font-size: 9px; font-weight: 600;
  border: 1px solid #C7D2FE;
}

.close-detail-btn {
  position: absolute; top: 12px; right: 12px;
  width: 26px; height: 26px; border: none;
  background: #F1F5F9; border-radius: 8px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  color: #64748B; transition: all 0.15s;
}
.close-detail-btn:hover { background: #E2E8F0; color: #334155; transform: rotate(90deg); }
</style>
