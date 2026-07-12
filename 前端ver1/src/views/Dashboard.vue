<template>
  <div class="dashboard-page">
    <el-alert
      v-if="dashboardError"
      type="error"
      :title="dashboardError"
      show-icon
      closable
      class="dashboard-error"
      @close="dashboardError = ''"
    />

    <div class="dashboard-grid">
      <aside class="col-left">
        <div class="panel panel-profile">
          <div class="panel-hd hd-purple">
            <el-icon :size="16"><User /></el-icon>
            <span>学习画像</span>
            <el-button text size="small" class="panel-link" @click="$router.push('/profile')">详情</el-button>
          </div>
          <div class="panel-bd">
            <AppSkeleton v-if="profileLoading" type="profile" />
            <template v-else-if="profile">
              <div class="profile-banner" />
              <div class="profile-avatar-wrap">
                <div class="profile-avatar">{{ uname.charAt(0).toUpperCase() }}</div>
              </div>
              <div class="profile-name">{{ uname }}</div>
              <div v-if="profile.cognitive_style" class="profile-tag">
                {{ styleLabel(profile.cognitive_style) }}
              </div>
              <div class="profile-stats">
                <div class="pstat">
                  <span class="pstat-val">{{ profile.weekly_hours || '--' }}h</span>
                  <span class="pstat-label">每周学习</span>
                </div>
                <div class="pstat">
                  <span class="pstat-val">{{ goalLabel(profile.learning_goal) || '暂无' }}</span>
                  <span class="pstat-label">学习目标</span>
                </div>
              </div>
            </template>
            <div v-else class="empty-mini">对话中采集画像</div>
          </div>
        </div>

        <div class="panel panel-path">
          <div class="panel-hd">
            <el-icon :size="16"><Guide /></el-icon>
            <span>学习路径</span>
            <el-button text size="small" class="panel-link" @click="$router.push('/learning-path')">详情</el-button>
          </div>
          <div class="panel-bd">
            <AppSkeleton v-if="pathLoading" type="list" :count="3" />
            <template v-else-if="pathPhases.length">
              <div v-for="(p, i) in pathPhases.slice(0, 3)" :key="i" class="path-step">
                <div class="path-step-num">{{ i + 1 }}</div>
                <div class="path-step-info">
                  <div class="path-step-name">{{ p.name }}</div>
                  <div class="path-step-meta">{{ p.count }}个知识点</div>
                </div>
              </div>
            </template>
            <div v-else class="empty-mini">对话中规划路径</div>
          </div>
        </div>

        <div class="panel panel-actions">
          <div class="panel-hd">
            <el-icon :size="16"><MagicStick /></el-icon>
            <span>快捷入口</span>
          </div>
          <div class="panel-bd actions-list">
            <button v-for="a in quickActions" :key="a.label" class="action-btn" :class="a.cls" @click="a.action">
              <el-icon :size="16"><component :is="a.icon" /></el-icon>
              <span>{{ a.label }}</span>
            </button>
          </div>
        </div>
      </aside>

      <main class="col-center">
        <div v-if="isNewUser" class="panel panel-welcome">
          <div class="welcome-body">
            <h3 class="welcome-title">
              <el-icon><Sunny /></el-icon>
              开始你的个性化学习之旅
            </h3>
            <p class="welcome-subtitle">三步开启AI辅助学习：</p>
            <div class="welcome-steps">
              <div class="welcome-step" @click="$router.push('/chat')">
                <div class="ws-num">1</div>
                <div class="ws-info">
                  <div class="ws-title">与AI对话</div>
                  <div class="ws-desc">告诉AI你的学习目标、风格和基础</div>
                </div>
                <el-icon :size="14"><ArrowRight /></el-icon>
              </div>
              <div class="welcome-step" @click="$router.push('/resources')">
                <div class="ws-num">2</div>
                <div class="ws-info">
                  <div class="ws-title">获取资源</div>
                  <div class="ws-desc">AI为你生成文档、思维导图、练习题</div>
                </div>
                <el-icon :size="14"><ArrowRight /></el-icon>
              </div>
              <div class="welcome-step" @click="$router.push('/assessment')">
                <div class="ws-num">3</div>
                <div class="ws-info">
                  <div class="ws-title">查看评估</div>
                  <div class="ws-desc">跟踪学习进度，获取能力评估报告</div>
                </div>
                <el-icon :size="14"><ArrowRight /></el-icon>
              </div>
            </div>
          </div>
        </div>

        <div v-if="suggestions.length > 0" class="panel panel-suggestions">
          <div class="panel-hd">
            <el-icon :size="16"><Promotion /></el-icon>
            <span>智能推荐</span>
            <span class="panel-hint">Agent 分析建议</span>
          </div>
          <div class="panel-bd">
            <div v-for="(sg, i) in suggestions.slice(0, 3)" :key="i" class="sg-item" @click="handleSuggestion(sg)">
              <el-icon :size="18" class="sg-icon"><component :is="sgIcon(sg.intent)" /></el-icon>
              <div class="sg-info">
                <span class="sg-reason">{{ sg.reason }}</span>
                <span class="sg-action">{{ sgLabel(sg.intent) }}</span>
              </div>
              <el-icon :size="14"><ArrowRight /></el-icon>
            </div>
          </div>
        </div>

        <div class="panel panel-agent-stats">
          <div class="panel-hd">
            <el-icon :size="16"><Connection /></el-icon>
            <span>Agent 调用统计</span>
          </div>
          <div class="panel-bd">
            <AppSkeleton v-if="agentStatsLoading" type="stat" :count="6" />
            <div v-else class="agent-stats-row">
              <div v-for="a in realAgentStats" :key="a.name" class="agent-stat-chip">
                <div class="asc-dot" :class="getDotClass(a.color)" />
                <span class="asc-name">{{ a.label }}</span>
                <span class="asc-count">{{ a.calls }}次</span>
              </div>
            </div>
          </div>
        </div>

        <div class="panel panel-content">
          <div class="panel-hd">
            <el-icon :size="16"><Reading /></el-icon>
            <span>最近学习资源</span>
            <el-button text size="small" class="panel-link" @click="$router.push('/resources')">全部</el-button>
          </div>
          <div class="panel-bd">
            <AppSkeleton v-if="resourcesLoading" type="list" :count="3" />
            <template v-else>
              <div v-if="recentResources.length === 0" class="empty-mini">暂无学习资源，去对话中生成</div>
              <div v-for="r in recentResources" :key="r.id" class="resource-mini" @click="$router.push(`/resources/${r.id}`)">
                <el-icon :size="20" :style="{ color: typeColor(r.resource_type) }">
                  <component :is="typeIcon(r.resource_type)" />
                </el-icon>
                <div class="resource-mini-info">
                  <span class="resource-mini-title">{{ r.title }}</span>
                  <span class="resource-mini-type">{{ typeLabel(r.resource_type) }}</span>
                </div>
                <span class="resource-mini-time">{{ timeAgo(r.created_at) }}</span>
              </div>
            </template>
          </div>
        </div>
      </main>

      <aside class="col-right">
        <div class="panel panel-bkt">
          <div class="panel-hd">
            <el-icon :size="16"><TrendCharts /></el-icon>
            <span>BKT 掌握率</span>
          </div>
          <div class="panel-bd bkt-scroll">
            <AppSkeleton v-if="masteryLoading" type="text" :lines="3" />
            <template v-else-if="masteryItems.length">
              <div v-for="m in masteryItems.slice(0, 4)" :key="m.name" class="bkt-row">
                <span class="bkt-name">{{ m.name }}</span>
                <div class="bkt-bar-wrap">
                  <div class="bkt-bar" :class="{ high: m.val >= 70, mid: m.val >= 40 && m.val < 70, low: m.val < 40 }" :style="{ width: m.val + '%' }" />
                </div>
                <span class="bkt-pct" :style="{ color: m.color }">{{ m.val }}%</span>
              </div>
            </template>
            <div v-else class="empty-mini">对话中采集BKT数据</div>
          </div>
        </div>

        <div class="panel panel-risk">
          <div class="panel-hd">
            <el-icon :size="16"><WarningFilled /></el-icon>
            <span>学习风险</span>
          </div>
          <div class="panel-bd risk-scroll">
            <div v-if="riskItems.length === 0" class="empty-mini safe">未检测到风险</div>
            <div v-for="r in riskItems" :key="r.name" class="risk-row" :class="r.level">
              <div class="risk-dot" />
              <div class="risk-info">
                <span class="risk-name">{{ r.name }}</span>
                <span class="risk-desc">{{ r.desc }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="panel panel-radar">
          <div class="panel-hd">
            <el-icon :size="16"><DataAnalysis /></el-icon>
            <span>能力分布</span>
          </div>
          <div class="panel-bd panel-radar-bd">
            <div ref="radarRef" style="height:180px" />
          </div>
        </div>

        <div class="panel panel-kb">
          <div class="panel-hd">
            <el-icon :size="16"><Coin /></el-icon>
            <span>知识库统计</span>
          </div>
          <div class="panel-bd kb-stats">
            <div class="kb-stat">
              <span class="kb-num" style="color: var(--primary)">{{ kbCount.toLocaleString() }}</span>
              <span class="kb-unit">条知识</span>
            </div>
            <div class="kb-stat">
              <span class="kb-num" style="color: var(--green)">{{ exCount }}</span>
              <span class="kb-unit">道习题</span>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import api from '@/api/index'
import { useLearningStore } from '@/stores/learning'
import AppSkeleton from '@/components/common/AppSkeleton.vue'

const router = useRouter()
const learningStore = useLearningStore()
const radarRef = ref<HTMLElement | null>(null)
const dashboardError = ref('')

interface Profile { cognitive_style?: string; learning_goal?: string; weekly_hours?: number; knowledge_base?: Record<string,number>; dimension_scores?: Record<string,number>; suggestions?: Array<{intent:string; reason:string; ts?:number}> }
interface ResourceItem { id: number; resource_type: string; title: string; created_at: string }
interface MasteryItem { name: string; val: number; label: string; color: string; barColor: string }
interface RiskItem { name: string; desc: string; level: string }

const uname = ref('同学')
const profile = ref<Profile | null>(null)
const profileLoading = ref(true)
const pathLoading = ref(true)
const masteryLoading = ref(true)
const resourcesLoading = ref(true)
const agentStatsLoading = ref(true)
const pathPhases = ref<{name:string;count:number}[]>([])
const masteryItems = ref<MasteryItem[]>([])
const riskItems = ref<RiskItem[]>([])
const recentResources = ref<ResourceItem[]>([])
const kbCount = ref(0)
const exCount = ref(0)

const realAgentStats = ref<{name:string;label:string;color:string;calls:number}[]>([
  { name:'supervisor', label:'调度器', color:'#2563EB', calls:0 },
  { name:'resource_agent', label:'资源', color:'#10B981', calls:0 },
  { name:'question_agent', label:'出题', color:'#F59E0B', calls:0 },
  { name:'path_agent', label:'路径', color:'#8B5CF6', calls:0 },
  { name:'evaluation_agent', label:'评估', color:'#3B82F6', calls:0 },
  { name:'profile_agent', label:'画像', color:'#0EA5E9', calls:0 },
])

const quickActions = [
  { label: '开始对话', icon: 'ChatDotRound', cls: 'primary', action: () => router.push('/chat') },
  { label: '生成资源', icon: 'FolderAdd', cls: 'green', action: () => router.push({ path: '/chat', query: { action: 'resource' } }) },
  { label: '开始练习', icon: 'EditPen', cls: 'orange', action: () => router.push({ path: '/chat', query: { action: 'question' } }) },
  { label: '查看评估', icon: 'DataAnalysis', cls: '', action: () => router.push('/assessment') },
]

const isNewUser = ref(false)
function checkNewUser() {
  const p = profile.value
  const hasProfileData = p && (
    p.cognitive_style ||
    p.learning_goal ||
    (p.weekly_hours && p.weekly_hours > 0) ||
    (p.knowledge_base && Object.keys(p.knowledge_base).length > 0)
  )
  const hasResources = recentResources.value.length > 0
  const hasBKT = masteryItems.value.length > 0
  isNewUser.value = !hasProfileData && !hasResources && !hasBKT
}

const suggestions = ref<any[]>([])

function loadSuggestions() {
  const s = profile.value?.suggestions
  if (Array.isArray(s) && s.length > 0) {
    const now = Date.now() / 1000
    suggestions.value = s.filter((sg: any) => !sg.ts || (now - sg.ts) < 86400)
  }
}

const SUGGESTION_ICONS: Record<string, string> = {
  evaluation: 'TrendCharts', resource: 'Reading', question: 'EditPen', path: 'Guide', profile: 'User'
}
function sgIcon(intent: string) { return SUGGESTION_ICONS[intent] || 'Connection' }

const SUGGESTION_ACTIONS: Record<string, string> = {
  evaluation: '查看评估 →', resource: '查看资源 →', question: '开始练习 →',
  path: '规划路径 →', profile: '完善画像 →'
}
function sgLabel(intent: string) { return SUGGESTION_ACTIONS[intent] || '去看看 →' }

function handleSuggestion(sg: any) {
  const routes: Record<string, string> = {
    evaluation: '/assessment', resource: '/resources', question: '/chat',
    path: '/learning-path', profile: '/profile'
  }
  router.push(routes[sg.intent] || '/chat')
}

function styleLabel(v?: string) {
  if (!v) return ''
  const map: Record<string,string> = { visual: '视觉型', auditory: '听觉型', kinesthetic: '动手型', reading: '阅读型' }
  if (map[v]) return map[v]
  if (/写代码|动手|敲|做项目|实践|操作|kinesthetic|hands.on/i.test(v)) return '动手型'
  if (/看|读|视觉|图|视频|visual|watch/i.test(v)) return '视觉型'
  if (/听|音频|auditory|listen/i.test(v)) return '听觉型'
  return v.length > 10 ? v.slice(0, 8) + '...' : v
}
function goalLabel(v?: string) {
  const map: Record<string,string> = { exam: '考试备考', skill: '技能提升', career: '职业发展', interest: '兴趣学习' }
  return map[v||''] || v || ''
}
function typeLabel(t: string) {
  const map: Record<string,string> = { document:'知识文档', mindmap:'思维导图', question_set:'练习题', code_example:'代码案例', video_script:'视频脚本' }
  return map[t] || t
}
function typeIcon(t: string) {
  const map: Record<string,string> = { document:'Document', mindmap:'DataBoard', question_set:'EditPen', code_example:'Monitor', video_script:'VideoPlay' }
  return map[t] || 'Document'
}
function typeColor(t: string) {
  const map: Record<string,string> = { document:'#2563EB', mindmap:'#10B981', question_set:'#F59E0B', code_example:'#8B5CF6', video_script:'#3B82F6' }
  return map[t] || '#3B82F6'
}
function timeAgo(dateStr: string) {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const min = Math.floor(diff/60000)
  if (min < 60) return min + '分钟前'
  const hr = Math.floor(min/60)
  if (hr < 24) return hr + '小时前'
  return Math.floor(hr/24) + '天前'
}
function getMasteryTheme(val: number): { color: string; barColor: string; label: string } {
  if (val >= 85) return { color: '#10B981', barColor: '#10B981', label: '精通' }
  if (val >= 60) return { color: '#2563EB', barColor: '#2563EB', label: '掌握' }
  if (val >= 35) return { color: '#F59E0B', barColor: '#F59E0B', label: '学习中' }
  return { color: '#8B5CF6', barColor: '#8B5CF6', label: '入门' }
}
function getDotClass(color: string): string {
  if (color === '#10B981') return 'green'
  if (color === '#2563EB') return 'blue'
  if (color === '#F59E0B') return 'orange'
  if (color === '#8B5CF6') return 'purple'
  if (color === '#3B82F6') return 'cyan'
  return 'sky'
}

async function loadAll() {
  try {
    const [userRes, profileRes, resourcesRes, adminRes] = await Promise.all([
      api.get('/auth/me'),
      api.get('/profile/me'),
      api.get('/resources?size=5'),
      api.get('/admin/stats'),
    ])

    uname.value = userRes.data.nickname || userRes.data.username || '同学'

    const p = profileRes.data
    profile.value = p
    profileLoading.value = false
    loadSuggestions()
    const kb = p.knowledge_base || {}
    const ds = p.dimension_scores || {}

    resourcesLoading.value = false
    recentResources.value = resourcesRes.data || []

    kbCount.value = adminRes.data?.knowledge_base || 0
    exCount.value = adminRes.data?.exercise_bank || 0

    try {
      await learningStore.fetchLearningPath()
      if (learningStore.pathPhases.length > 0) {
        pathPhases.value = learningStore.pathPhases
      }
    } catch {}
    pathLoading.value = false

    const bktRes = await api.get('/bkt/status').catch(() => ({ data: null }))
    const bktConcepts = (bktRes.data?.concepts || []) as Array<{ name: string; p_known: number; level?: string }>
    let items: MasteryItem[]
    if (bktConcepts.length > 0) {
      items = bktConcepts
        .sort((a, b) => b.p_known - a.p_known)
        .map(c => {
          const v = Math.round(c.p_known * 100)
          return { name: c.name, val: v, ...getMasteryTheme(v) }
        })
    } else {
      items = Object.entries(kb)
        .sort(([,a],[,b]) => (b as number) - (a as number))
        .map(([name, val]) => {
          const v = Number(val) || 0
          return { name, val: v, ...getMasteryTheme(v) }
        })
    }
    masteryItems.value = items
    masteryLoading.value = false

    if (bktConcepts.length > 0) {
      const weakConcepts = bktConcepts.filter(c => c.p_known < 0.35)
      riskItems.value = weakConcepts.map(c => ({
        name: c.name,
        desc: `掌握概率仅${Math.round(c.p_known * 100)}%，建议加强练习`,
        level: c.p_known < 0.2 ? 'high' : 'medium',
      }))
    } else {
      riskItems.value = items
        .filter(m => m.val < 35)
        .map(m => ({ name: m.name, desc: `掌握率仅${m.val}%，建议加强学习`, level: m.val < 20 ? 'high' : 'medium' }))
    }

    let radarDs = ds
    if (Object.keys(radarDs).length === 0 && bktConcepts.length > 0) {
      const avgMastery = Math.round((bktRes.data?.average_mastery || 0) * 100)
      const sorted = [...bktConcepts].sort((a, b) => (b.p_known || 0) - (a.p_known || 0))
      const totalCount = sorted.length
      const masteredCount = sorted.filter(c => (c.p_known || 0) >= 0.7).length
      const learningCount = sorted.filter(c => (c.p_known || 0) >= 0.35).length
      const masteredPct = totalCount > 0 ? Math.round((masteredCount / totalCount) * 100) : 0
      const learningPct = totalCount > 0 ? Math.round((learningCount / totalCount) * 100) : 0
      const topHalf = sorted.slice(0, Math.max(1, Math.ceil(totalCount / 2)))
      const topHalfAvg = Math.round(
        topHalf.reduce((s, c) => s + (c.p_known || 0), 0) / topHalf.length * 100
      )
      const mean = sorted.reduce((s, c) => s + (c.p_known || 0), 0) / Math.max(totalCount, 1)
      const variance = sorted.reduce((s, c) => {
        const d = (c.p_known || 0) - mean
        return s + d * d
      }, 0) / Math.max(totalCount, 1)
      const cv = mean > 0 ? Math.sqrt(variance) / mean : 1

      radarDs = {
        knowledge: avgMastery,
        speed: Math.min(100, Math.round(learningPct * 0.9 + (totalCount >= 5 ? 10 : totalCount * 2))),
        practice: Math.min(100, Math.round(masteredPct * 0.85 + Math.min(15, totalCount * 2))),
        focus: Math.min(100, Math.round(topHalfAvg * 0.9 + (totalCount >= 3 ? 10 : 0))),
        logic: Math.min(100, Math.round(avgMastery * (1 - Math.min(0.5, cv * 0.6)) + 10)),
        overall: Math.round(avgMastery * 0.3 + learningPct * 0.25 + masteredPct * 0.25 + topHalfAvg * 0.2),
      }
    }
    checkNewUser()
    if (Object.keys(radarDs).length > 0) renderRadar(radarDs)

  } catch (e) {
    dashboardError.value = '数据加载失败，请检查网络连接后刷新页面重试'
    profileLoading.value = false
    masteryLoading.value = false
    pathLoading.value = false
    resourcesLoading.value = false
    checkNewUser()
  }
}

const radarLabelMap: Record<string, string> = {
  knowledge: '知识掌握',
  overall: '综合能力',
  logic: '逻辑思维',
  focus: '专注程度',
  practice: '实践应用',
  speed: '学习效率',
}

function renderRadar(ds: Record<string, number>) {
  nextTick(() => {
    if (!radarRef.value) return
    const el = radarRef.value
    if (el.clientWidth === 0 || el.clientHeight === 0) {
      const ro = new ResizeObserver(() => {
        if (el.clientWidth > 0 && el.clientHeight > 0) {
          ro.disconnect()
          renderRadar(ds)
        }
      })
      ro.observe(el)
      return
    }
    interface ChartElement extends HTMLElement { _chart?: echarts.ECharts }
    const existing = (el as ChartElement)._chart
    if (existing) { existing.dispose() }
    const chart = echarts.init(el)
    const indicators = Object.entries(ds).map(([k]) => ({
      name: radarLabelMap[k] || k,
      max: 100,
    }))
    chart.setOption({
      radar: {
        center: ['50%', '50%'],
        radius: '60%',
        indicator: indicators,
        axisName: {
          color: '#334155',
          fontSize: 11,
          fontWeight: 500,
          padding: [2, 3],
        },
        splitArea: {
          areaStyle: {
            color: ['#F8FAFC', '#F1F5F9', '#F8FAFC', '#F1F5F9'],
          },
        },
        axisLine: { lineStyle: { color: 'var(--border)', width: 1 } },
        splitLine: { lineStyle: { color: 'var(--border)', width: 1 } },
        axisTick: { show: false },
      },
      series: [{
        type: 'radar',
        data: [{
          value: Object.values(ds),
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(37,99,235,.20)' },
              { offset: 1, color: 'rgba(37,99,235,.05)' },
            ]),
          },
          lineStyle: { color: '#2563EB', width: 2, cap: 'round' },
          itemStyle: {
            color: '#2563EB',
            borderColor: '#fff',
            borderWidth: 1.5,
          },
          symbol: 'circle',
          symbolSize: 5,
        }],
        animationDuration: 1000,
        animationEasing: 'cubicOut',
      }],
    })
    ;(el as ChartElement)._chart = chart
  })
}

async function loadAgentStats() {
  agentStatsLoading.value = true
  try {
    const r = await api.get('/chat/history', { params: { limit: 100 } })
    const history: Array<{ role?: string; agent_type?: string }> = r.data || []
    const counts: Record<string, number> = {}
    for (const h of history) {
      if (h.agent_type) {
        counts[h.agent_type] = (counts[h.agent_type] || 0) + 1
      }
    }
    realAgentStats.value.forEach(a => {
      a.calls = counts[a.name] || 0
    })
  } catch {
    // non-critical
  } finally {
    agentStatsLoading.value = false
  }
}

onMounted(() => { loadAll(); loadAgentStats() })
</script>

<style scoped>
.dashboard-page {
  padding: var(--space-md);
  height: 100%;
  box-sizing: border-box;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.dashboard-error {
  margin-bottom: var(--space-md);
  flex-shrink: 0;
}

.dashboard-grid {
  display: flex;
  gap: var(--space-md);
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.col-left {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 2px;
}
.col-center {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0 2px;
}
.col-right {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding-left: 2px;
}

.panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--transition-fast), border-color var(--transition-fast);
  flex-shrink: 0;
}
.panel:hover {
  box-shadow: var(--shadow-md);
  border-color: rgba(37,99,235,.15);
}

.panel-hd {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--border);
  font-size: var(--font-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.panel-hd .el-icon {
  color: var(--primary);
}
.panel-link {
  margin-left: auto;
  font-size: var(--font-xs) !important;
  color: var(--text-muted) !important;
}
.panel-link:hover {
  color: var(--primary) !important;
}
.panel-hint {
  margin-left: auto;
  font-size: var(--font-xs);
  color: var(--text-muted);
  font-weight: 400;
}
.panel-bd {
  padding: var(--space-md);
}

.empty-mini {
  font-size: var(--font-xs);
  color: var(--text-muted);
  text-align: center;
  padding: var(--space-xl) 0;
}
.empty-mini.safe {
  color: var(--green);
}

.panel-profile .panel-hd {
  padding-bottom: var(--space-md);
}

.profile-banner {
  height: 52px;
  margin: 0 calc(-1 * var(--space-md)) 0;
  background: linear-gradient(135deg, var(--primary), var(--blue-indigo));
}

.panel-profile .panel-bd {
  padding-top: 0;
  position: relative;
}

.profile-avatar-wrap {
  position: relative;
  margin-top: -22px;
  display: flex;
  justify-content: center;
}
.profile-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--bg-card);
  color: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-lg);
  font-weight: 700;
  border: 3px solid var(--bg-card);
  box-shadow: var(--shadow-sm);
  z-index: 1;
}
.profile-name {
  text-align: center;
  font-size: var(--font-base);
  font-weight: 600;
  color: var(--text-primary);
  margin-top: var(--space-sm);
}
.profile-tag {
  display: table;
  margin: var(--space-xs) auto 0;
  padding: 3px 10px;
  background: var(--primary-light);
  color: var(--primary);
  border-radius: var(--radius-xl);
  font-size: var(--font-xs);
  font-weight: 500;
}
.profile-stats {
  display: flex;
  justify-content: center;
  gap: var(--space-xl);
  margin-top: var(--space-md);
  padding-top: var(--space-md);
  border-top: 1px dashed var(--border);
}
.pstat {
  text-align: center;
}
.pstat-val {
  font-size: var(--font-xl);
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}
.pstat-label {
  display: block;
  font-size: var(--font-xs);
  color: var(--text-muted);
  margin-top: 2px;
}

.path-step {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
  margin-bottom: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-muted);
  border-radius: var(--radius-md);
  transition: background var(--transition-fast);
}
.path-step:last-child {
  margin-bottom: 0;
}
.path-step:hover {
  background: var(--primary-light);
}
.path-step-num {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  background: var(--primary);
  color: #fff;
  font-size: var(--font-xs);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.path-step-info {
  min-width: 0;
}
.path-step-name {
  font-size: var(--font-sm);
  font-weight: 500;
  color: var(--text-primary);
}
.path-step-meta {
  font-size: var(--font-xs);
  color: var(--text-muted);
}

.actions-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}
.action-btn {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 10px var(--space-md);
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: var(--font-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  width: 100%;
}
.action-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--primary-light);
}
.action-btn.primary {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}
.action-btn.primary:hover {
  background: var(--primary-hover);
}
.action-btn.green {
  background: var(--green-lighter);
  color: var(--green);
  border-color: rgba(16,185,129,.2);
}
.action-btn.green:hover {
  background: var(--green);
  color: #fff;
  border-color: var(--green);
}
.action-btn.orange {
  background: var(--orange-lighter);
  color: var(--orange);
  border-color: rgba(245,158,11,.2);
}
.action-btn.orange:hover {
  background: var(--orange);
  color: #fff;
  border-color: var(--orange);
}
.action-btn .el-icon {
  opacity: 0.8;
}
.action-btn:hover .el-icon {
  opacity: 1;
}

.panel-hd.hd-purple .el-icon { color: var(--purple); }
.panel-hd.hd-green .el-icon { color: var(--green); }
.panel-hd.hd-orange .el-icon { color: var(--orange); }
.panel-hd.hd-blue .el-icon { color: var(--primary); }
.panel-hd.hd-red .el-icon { color: var(--red); }

.panel-welcome {
  border-color: rgba(37,99,235,.2);
  background: linear-gradient(135deg, #EFF6FF 0%, #F0F5FF 100%);
}
.welcome-body {
  padding: var(--space-lg) var(--space-lg) var(--space-md);
}
.welcome-title {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-xs);
}
.welcome-title .el-icon {
  color: var(--orange);
  font-size: var(--font-xl);
}
.welcome-subtitle {
  margin: 0 0 var(--space-md);
  font-size: var(--font-sm);
  color: var(--text-secondary);
}
.welcome-steps {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}
.welcome-step {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.welcome-step:hover {
  border-color: var(--primary);
  background: #FAFCFF;
  transform: translateX(2px);
  box-shadow: var(--shadow-sm);
}
.welcome-step:hover .ws-num {
  background: var(--primary);
  transform: scale(1.05);
}
.ws-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: var(--font-sm);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all var(--transition-fast);
}
.ws-info {
  flex: 1;
  min-width: 0;
}
.ws-title {
  font-size: var(--font-base);
  font-weight: 600;
  color: var(--text-primary);
}
.ws-desc {
  font-size: var(--font-xs);
  color: var(--text-muted);
  margin-top: 2px;
}
.welcome-step .el-icon {
  color: var(--text-muted);
  flex-shrink: 0;
}

.panel-suggestions {
  border: 1px solid var(--border);
}
.sg-item {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md);
  margin-bottom: var(--space-sm);
  background: var(--bg-page);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.sg-item:last-child {
  margin-bottom: 0;
}
.sg-item:hover {
  border-color: var(--primary);
  background: var(--primary-light);
}
.sg-icon {
  color: var(--primary);
  flex-shrink: 0;
}
.sg-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.sg-reason {
  font-size: var(--font-sm);
  color: var(--text-primary);
  line-height: 1.4;
}
.sg-action {
  font-size: var(--font-xs);
  color: var(--primary);
  font-weight: 600;
}

.agent-stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-sm);
}
.agent-stat-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  background: var(--bg-muted);
  border: 1px solid var(--border);
  transition: all var(--transition-fast);
}
.agent-stat-chip:hover {
  background: var(--bg-card);
  border-color: var(--primary-light);
}
.asc-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.asc-dot.green { background: var(--green); box-shadow: 0 0 6px var(--green-glow); }
.asc-dot.blue { background: var(--primary); box-shadow: 0 0 6px rgba(37,99,235,.3); }
.asc-dot.orange { background: var(--orange); box-shadow: 0 0 6px var(--orange-glow); }
.asc-dot.purple { background: var(--purple); box-shadow: 0 0 6px var(--purple-glow); }
.asc-dot.cyan { background: var(--blue-sky); box-shadow: 0 0 6px rgba(14,165,233,.3); }
.asc-dot.sky { background: var(--blue-indigo); box-shadow: 0 0 6px rgba(99,102,241,.3); }
.asc-name {
  font-size: var(--font-xs);
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.asc-count {
  margin-left: auto;
  font-size: var(--font-sm);
  font-weight: 600;
  color: var(--text-primary);
  flex-shrink: 0;
}

.resource-mini {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background var(--transition-fast);
  border-left: 3px solid transparent;
  margin: 0 calc(-1 * var(--space-md));
  padding-left: calc(var(--space-md) - 3px);
  padding-right: var(--space-md);
}
.resource-mini:last-child {
  border-bottom: none;
}
.resource-mini:hover {
  background: var(--bg-muted);
  border-left-color: var(--primary);
}

.resource-mini .el-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-muted);
  flex-shrink: 0;
  padding: 8px;
  box-sizing: border-box;
}
.resource-mini-info {
  flex: 1;
  min-width: 0;
}
.resource-mini-title {
  font-size: var(--font-sm);
  font-weight: 500;
  color: var(--text-primary);
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.resource-mini-type {
  font-size: var(--font-xs);
  color: var(--text-muted);
  margin-top: 2px;
}
.resource-mini-time {
  font-size: var(--font-xs);
  color: var(--text-muted);
  flex-shrink: 0;
}

.bkt-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}
.bkt-row:last-child {
  margin-bottom: 0;
}
.bkt-name {
  width: 60px;
  font-size: var(--font-xs);
  font-weight: 500;
  color: var(--text-secondary);
  text-align: right;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bkt-bar-wrap {
  flex: 1;
  min-width: 0;
  height: 8px;
  background: var(--bg-muted);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.bkt-bar {
  height: 100%;
  border-radius: var(--radius-sm);
  transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}
.bkt-bar.high { background: var(--green); }
.bkt-bar.mid { background: var(--primary); }
.bkt-bar.low { background: var(--orange); }
.bkt-pct {
  width: 34px;
  font-size: var(--font-xs);
  font-weight: 600;
  flex-shrink: 0;
  text-align: right;
}

.risk-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
  border-bottom: 1px solid var(--border);
}
.risk-row:last-child {
  border-bottom: none;
}
.risk-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 4px;
  flex-shrink: 0;
}
.risk-row.high .risk-dot { background: var(--red); box-shadow: 0 0 6px var(--red-glow); }
.risk-row.medium .risk-dot { background: var(--orange); box-shadow: 0 0 6px var(--orange-glow); }
.risk-row.low .risk-dot { background: var(--green); box-shadow: 0 0 6px var(--green-glow); }
.risk-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.risk-name {
  font-size: var(--font-xs);
  font-weight: 600;
  color: var(--text-primary);
}
.risk-desc {
  font-size: var(--font-xs);
  color: var(--text-muted);
  line-height: 1.4;
}

.risk-scroll {
  max-height: 160px;
  overflow-y: auto;
  overflow-x: hidden;
}
.bkt-scroll {
  max-height: 160px;
  overflow-y: auto;
  overflow-x: hidden;
}

.panel-radar-bd {
  padding: var(--space-sm);
}

.kb-stats {
  display: flex;
  justify-content: space-around;
  padding: var(--space-sm) 0;
}
.kb-stat {
  text-align: center;
  position: relative;
  flex: 1;
}
.kb-stat:first-child::after {
  content: '';
  position: absolute;
  right: 0;
  top: 15%;
  width: 1px;
  height: 50%;
  background: var(--border);
}
.kb-num {
  font-size: var(--font-2xl);
  font-weight: 700;
  line-height: 1.2;
}
.kb-unit {
  display: block;
  font-size: var(--font-xs);
  color: var(--text-muted);
  margin-top: 2px;
}

@media (max-width: 1200px) {
  .col-right {
    display: none;
  }
}

@media (max-width: 768px) {
  .dashboard-page {
    padding: var(--space-sm);
    height: auto;
    min-height: calc(100dvh - var(--header-h));
    overflow-y: auto;
  }
  .dashboard-grid {
    flex-direction: column;
    height: auto;
    gap: var(--space-sm);
    overflow: visible;
  }
  .col-left,
  .col-center,
  .col-right {
    width: 100%;
    height: auto;
    overflow: visible;
    padding: 0;
  }
  .agent-stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .action-btn {
    padding: var(--space-md);
  }
}

@media (max-width: 480px) {
  .agent-stats-row {
    grid-template-columns: 1fr 1fr;
    gap: var(--space-xs);
  }
  .agent-stat-chip {
    padding: var(--space-xs) var(--space-sm);
  }
}
</style>
