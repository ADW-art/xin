<template>
  <div class="intelligence-center">
    <!-- 页面级错误提示 -->
    <el-alert
      v-if="dashboardError"
      type="error"
      :title="dashboardError"
      show-icon
      closable
      class="dashboard-error"
      @close="dashboardError = ''"
    />
    <!-- ═══════════════════════ LEFT COLUMN ═══════════════════════ -->
    <aside class="col-left">
      <!-- 学习画像迷你卡片 -->
      <div class="panel panel-profile">
        <div class="panel-hd">
          <el-icon :size="16"><User /></el-icon>
          <span>学习画像</span>
          <el-button text size="small" class="panel-link" @click="$router.push('/profile')">详情</el-button>
        </div>
        <div class="panel-bd">
          <div v-if="profileLoading" class="skeleton-text" />
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
          <div v-else class="empty-mini">对话中采集</div>
        </div>
      </div>

      <!-- 当前知识图谱路径摘要 -->
      <div class="panel panel-path">
        <div class="panel-hd">
          <el-icon :size="16"><Guide /></el-icon>
          <span>知识图谱</span>
          <el-button text size="small" class="panel-link" @click="$router.push('/learning-path')">详情</el-button>
        </div>
        <div class="panel-bd">
          <div v-if="pathLoading" class="skeleton-text" />
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

      <!-- 快捷操作 -->
      <div class="panel panel-actions">
        <div class="panel-hd">
          <el-icon :size="16"><Connection /></el-icon>
          <span>快捷操作</span>
        </div>
        <div class="panel-bd actions-list">
          <button v-for="a in quickActions" :key="a.label" class="action-btn" :class="a.cls" @click="a.action">
            <el-icon :size="16"><component :is="a.icon" /></el-icon>
            <span>{{ a.label }}</span>
          </button>
        </div>
      </div>
    </aside>

    <!-- ═══════════════════════ CENTER COLUMN ═══════════════════════ -->
    <main class="col-center">
      <!-- 新用户引导卡片 -->
      <div v-if="isNewUser" class="panel panel-welcome">
        <div class="panel-hd">
          <el-icon :size="16"><Sunny /></el-icon>
          <span>欢迎来到 A3 学习系统</span>
        </div>
        <div class="panel-bd welcome-body">
          <p class="welcome-subtitle">开始你的个性化学习之旅，只需三步：</p>
          <div class="welcome-steps">
            <div class="welcome-step" @click="$router.push('/chat')">
              <div class="ws-num">1</div>
              <div class="ws-info">
                <div class="ws-title">填写学习画像</div>
                <div class="ws-desc">告诉AI你的学习目标、风格和时间安排</div>
              </div>
              <el-icon :size="14"><ArrowRight /></el-icon>
            </div>
            <div class="welcome-step" @click="$router.push('/chat')">
              <div class="ws-num">2</div>
              <div class="ws-info">
                <div class="ws-title">生成学习资料</div>
                <div class="ws-desc">让AI为你生成个性化教材、思维导图和练习题</div>
              </div>
              <el-icon :size="14"><ArrowRight /></el-icon>
            </div>
            <div class="welcome-step" @click="$router.push('/assessment')">
              <div class="ws-num">3</div>
              <div class="ws-info">
                <div class="ws-title">查看学习报告</div>
                <div class="ws-desc">评估学习效果，获取改进建议</div>
              </div>
              <el-icon :size="14"><ArrowRight /></el-icon>
            </div>
          </div>
        </div>
      </div>

      <!-- Agent 调用统计 (真实数据: chat history agent_type 计数) -->
      <div class="panel panel-agent-stats">
        <div class="panel-hd">
          <el-icon :size="16"><Connection /></el-icon>
          <span>Agent 调用统计</span>
          <span class="panel-hint">来源: 全量历史记录 (agent_type)</span>
        </div>
        <div class="agent-stats-row">
          <div v-for="a in realAgentStats" :key="a.name" class="agent-stat-chip">
            <div class="asc-dot" :class="{ green: a.color === '#10B981', blue: a.color === '#2563EB', orange: a.color === '#F59E0B', purple: a.color === '#8B5CF6' }" />
            <span class="asc-name">{{ a.label }}</span>
            <span class="asc-count">{{ a.calls }}次</span>
          </div>
        </div>
      </div>

      <!-- 当前学习内容 -->
      <div class="panel panel-content">
        <div class="panel-hd">
          <el-icon :size="16"><Reading /></el-icon>
          <span>学习内容</span>
          <el-button text size="small" class="panel-link" @click="$router.push('/resources')">全部</el-button>
        </div>
        <div class="panel-bd">
          <div v-if="recentResources.length === 0" class="empty-mini">对话中生成学习资料</div>
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
        </div>
      </div>
    </main>

    <!-- ═══════════════════════ RIGHT COLUMN ═══════════════════════ -->
    <aside class="col-right">
      <!-- BKT 知识掌握率 -->
      <div class="panel panel-bkt">
        <div class="panel-hd">
          <el-icon :size="16"><TrendCharts /></el-icon>
          <span>BKT 掌握率</span>
        </div>
        <div class="panel-bd bkt-scroll">
          <div v-if="masteryLoading" class="skeleton-text" />
          <template v-else-if="masteryItems.length">
            <div v-for="m in masteryItems.slice(0, 3)" :key="m.name" class="bkt-row">
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

      <!-- 学习风险预警 -->
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

      <!-- 能力雷达图 -->
      <div class="panel panel-radar">
        <div class="panel-hd">
          <el-icon :size="16"><DataAnalysis /></el-icon>
          <span>能力分布</span>
        </div>
        <div class="panel-bd panel-radar-bd">
          <div ref="radarRef" style="height:180px" />
        </div>
      </div>

      <!-- 知识库状态 -->
      <div class="panel panel-kb">
        <div class="panel-hd">
          <el-icon :size="16"><Coin /></el-icon>
          <span>知识库</span>
        </div>
        <div class="panel-bd kb-stats">
          <div class="kb-stat">
            <span class="kb-num">{{ kbCount.toLocaleString() }}</span>
            <span class="kb-unit">条知识</span>
          </div>
          <div class="kb-stat">
            <span class="kb-num">{{ exCount }}</span>
            <span class="kb-unit">道习题</span>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import api from '@/api/index'
import { useLearningStore } from '@/stores/learning'
const router = useRouter()
const learningStore = useLearningStore()
const radarRef = ref<HTMLElement | null>(null)
const dashboardError = ref('')

// ═══════════ Types ═══════════
interface Profile { cognitive_style?: string; learning_goal?: string; weekly_hours?: number; knowledge_base?: Record<string,number>; dimension_scores?: Record<string,number> }
interface ResourceItem { id: number; resource_type: string; title: string; created_at: string }
interface MasteryItem { name: string; val: number; label: string; color: string; barColor: string }
interface RiskItem { name: string; desc: string; level: string }
// ═══════════ State ═══════════
const uname = ref('同学')
const profile = ref<Profile | null>(null)
const profileLoading = ref(true)
const pathLoading = ref(true)
const masteryLoading = ref(true)
const pathPhases = ref<{name:string;count:number}[]>([])
const masteryItems = ref<MasteryItem[]>([])
const riskItems = ref<RiskItem[]>([])
const recentResources = ref<ResourceItem[]>([])
const kbCount = ref(0)
const exCount = ref(0)

// Agent 调用统计 (真实数据: chat_history.agent_type)
const realAgentStats = ref<{name:string;label:string;color:string;calls:number}[]>([
  { name:'supervisor', label:'Supervisor', color:'#2563EB', calls:0 },
  { name:'resource_agent', label:'Resource', color:'#10B981', calls:0 },
  { name:'question_agent', label:'Question', color:'#F59E0B', calls:0 },
  { name:'path_agent', label:'Path', color:'#8B5CF6', calls:0 },
  { name:'evaluation_agent', label:'Evaluation', color:'#3B82F6', calls:0 },
  { name:'profile_agent', label:'Profile', color:'#60A5FA', calls:0 },
])

// Quick actions (all navigate to functional routes)
const quickActions = [
  { label: '开始对话', icon: 'ChatDotRound', cls: 'primary', action: () => router.push('/chat') },
  { label: '生成资源', icon: 'MagicStick', cls: '', action: () => router.push('/chat?intent=resource') },
  { label: '开始练习', icon: 'EditPen', cls: '', action: () => router.push('/chat?intent=question') },
  { label: '规划路径', icon: 'Guide', cls: '', action: () => router.push('/learning-path') },
]

// New user detection: no profile data, no resources, no BKT data
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

// ═══════════ Helpers ═══════════
function styleLabel(v?: string) {
  const map: Record<string,string> = { visual: '视觉型', auditory: '听觉型', kinesthetic: '动手型', reading: '阅读型' }
  return map[v||''] || v || ''
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

// ═══════════ Data Loading ═══════════
async function loadAll() {
  try {
    const [userRes, profileRes, resourcesRes, adminRes, bktRes] = await Promise.all([
      api.get('/auth/me'),
      api.get('/profile/me'),
      api.get('/resources?size=5'),
      api.get('/admin/stats'),
      api.get('/bkt/status').catch(() => ({ data: null })),
    ])

    // User
    uname.value = userRes.data.nickname || userRes.data.username || '同学'

    // Profile
    const p = profileRes.data
    profile.value = p
    profileLoading.value = false
    const kb = p.knowledge_base || {}
    const ds = p.dimension_scores || {}

    // BKT Mastery — 优先使用 BKT 贝叶斯后验，回退到 profile knowledge_base
    const bktConcepts = (bktRes.data?.concepts || []) as Array<{ name: string; p_known: number; level?: string }>
    let items: MasteryItem[]
    if (bktConcepts.length > 0) {
      // 使用 BKT 真实贝叶斯概率（非简单累加值）
      items = bktConcepts
        .sort((a, b) => b.p_known - a.p_known)
        .map(c => {
          const v = Math.round(c.p_known * 100)
          return { name: c.name, val: v, ...getMasteryTheme(v) }
        })
    } else {
      // 回退：profile knowledge_base（简单累加值）
      items = Object.entries(kb)
        .sort(([,a],[,b]) => (b as number) - (a as number))
        .map(([name, val]) => {
          const v = Number(val) || 0
          return { name, val: v, ...getMasteryTheme(v) }
        })
    }
    masteryItems.value = items
    masteryLoading.value = false

    // Risk items — from BKT weak nodes or low profile knowledge_base
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

    // Resources
    recentResources.value = resourcesRes.data || []

    // KB stats
    kbCount.value = adminRes.data?.knowledge_base || 0
    exCount.value = adminRes.data?.exercise_bank || 0

    // Knowledge graph phases from backend (via learning store)
    try {
      await learningStore.fetchLearningPath()
      if (learningStore.pathPhases.length > 0) {
        pathPhases.value = learningStore.pathPhases
      }
    } catch {
      // Path loading failed, leave empty
    }
    pathLoading.value = false

    // Radar — 优先使用 profile dimension_scores，回退到 BKT 真实数据
    let radarDs = ds
    if (Object.keys(radarDs).length === 0 && bktConcepts.length > 0) {
      // 从 BKT 贝叶斯后验分布推导 6 维能力值（而非硬编码 0.8/0.9 系数）
      const avgMastery = Math.round((bktRes.data?.average_mastery || 0) * 100)
      const sorted = [...bktConcepts].sort((a, b) => (b.p_known || 0) - (a.p_known || 0))
      const totalCount = sorted.length

      // 分层统计：已掌握(>=0.7)、学习中(0.35-0.7)、入门(<0.35)
      const masteredCount = sorted.filter(c => (c.p_known || 0) >= 0.7).length
      const learningCount = sorted.filter(c => (c.p_known || 0) >= 0.35).length
      const masteredPct = totalCount > 0 ? Math.round((masteredCount / totalCount) * 100) : 0
      const learningPct = totalCount > 0 ? Math.round((learningCount / totalCount) * 100) : 0

      // 深度指标：前一半概念的均值（反映深度学习程度）
      const topHalf = sorted.slice(0, Math.max(1, Math.ceil(totalCount / 2)))
      const topHalfAvg = Math.round(
        topHalf.reduce((s, c) => s + (c.p_known || 0), 0) / topHalf.length * 100
      )

      // 离散度：标准差越小说明掌握越均匀（逻辑性强），越大说明偏科
      const mean = sorted.reduce((s, c) => s + (c.p_known || 0), 0) / Math.max(totalCount, 1)
      const variance = sorted.reduce((s, c) => {
        const d = (c.p_known || 0) - mean
        return s + d * d
      }, 0) / Math.max(totalCount, 1)
      const cv = mean > 0 ? Math.sqrt(variance) / mean : 1  // 变异系数

      radarDs = {
        // knowledge: BKT 贝叶斯后验均值 — 最直接的知识掌握度量
        knowledge: avgMastery,
        // speed: 学习效率 — 正在学习及以上层级的比例反映进步速度
        speed: Math.min(100, Math.round(learningPct * 0.9 + (totalCount >= 5 ? 10 : totalCount * 2))),
        // practice: 实践应用 — 已掌握比例 + 追踪概念数加成（多练多得）
        practice: Math.min(100, Math.round(masteredPct * 0.85 + Math.min(15, totalCount * 2))),
        // focus: 专注深度 — 前半段概念的均值反映深度学习质量
        focus: Math.min(100, Math.round(topHalfAvg * 0.9 + (totalCount >= 3 ? 10 : 0))),
        // logic: 逻辑思维 — 掌握越均匀(低变异系数)说明逻辑越强，偏科会拉低
        logic: Math.min(100, Math.round(avgMastery * (1 - Math.min(0.5, cv * 0.6)) + 10)),
        // overall: 综合能力 — 知识+速度+实践+逻辑 加权平均
        overall: Math.round(avgMastery * 0.3 + learningPct * 0.25 + masteredPct * 0.25 + topHalfAvg * 0.2),
      }
    }
    if (Object.keys(radarDs).length > 0) renderRadar(radarDs)

  } catch (e) {
    dashboardError.value = '数据加载失败，请检查网络连接后刷新页面重试'
    profileLoading.value = false
    masteryLoading.value = false
    pathLoading.value = false

    // New user detection
    checkNewUser()
  }
}

// ═══════════ ECharts Radar ═══════════
// 中文标签映射
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
    const chart = echarts.init(radarRef.value)
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
          color: '#64748B',
          fontSize: 11,
          fontWeight: 500,
          padding: [2, 3],
        },
        splitArea: {
          areaStyle: {
            color: ['#F8FAFC', '#F1F5F9', '#F8FAFC', '#F1F5F9'],
            shadowColor: 'rgba(0,0,0,.02)',
            shadowBlur: 4,
          },
        },
        axisLine: { lineStyle: { color: '#CBD5E1', width: 1 } },
        splitLine: { lineStyle: { color: '#E2E8F0', width: 1 } },
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
            shadowColor: 'rgba(37,99,235,.25)',
            shadowBlur: 4,
          },
          symbol: 'circle',
          symbolSize: 5,
        }],
        animationDuration: 1000,
        animationEasing: 'cubicOut',
      }],
    })
    interface ChartElement extends HTMLElement { _chart?: echarts.ECharts }
    ;(radarRef.value as ChartElement)._chart = chart
  })
}

// Fill real agent stats from ALL chat history (persistent across sessions/refreshes)
async function loadAgentStats() {
  try {
    // Fetch enough history to get a meaningful count; the backend stores
    // agent_type on each assistant message since conversation creation.
    const r = await api.get('/chat/history', { params: { limit: 100 } })
    const history: Array<{ role?: string; agent_type?: string }> = r.data || []
    const counts: Record<string, number> = {}
    for (const h of history) {
      // agent_type is only set on assistant messages; user messages have null
      if (h.agent_type) {
        counts[h.agent_type] = (counts[h.agent_type] || 0) + 1
      }
    }
    // Map backend agent_type values to display entries
    realAgentStats.value.forEach(a => {
      a.calls = counts[a.name] || 0
    })
    // If we received history but every stat is still 0, log the raw response
    // so the developer can see whether agent_type is really missing.
    if (history.length > 0 && realAgentStats.value.every(a => a.calls === 0)) {
      console.warn('[Dashboard] 对话历史已加载但 agent_type 全部为空，样本记录:', history.slice(0, 3))
    }
  } catch (e: unknown) {
    // Non-fatal: agent stats are supplemental, not critical
    const msg = e instanceof Error ? e.message : String(e)
    console.warn('[Dashboard] Agent 统计加载失败:', msg)
  }
}

onMounted(() => { loadAll(); loadAgentStats() })
</script>

<style scoped>
/* ═══════════ Layout ═══════════ */
.intelligence-center {
  display: flex;
  gap: 16px;
  padding: 18px;
  height: 100%;
  overflow: hidden;
  background: var(--bg-page);
  box-sizing: border-box;
}

.col-left { width: 252px; flex-shrink: 0; display: flex; flex-direction: column; gap: 12px; height: 100%; overflow-y: auto; overflow-x: hidden; }
.col-center { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; height: 100%; overflow-y: auto; overflow-x: hidden; }
.col-right { width: 286px; flex-shrink: 0; display: flex; flex-direction: column; gap: 12px; height: 100%; overflow-y: auto; overflow-x: hidden; }

/* ═══════════ Panel ═══════════ */
.panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-xs);
}
.panel:hover { box-shadow: var(--shadow-sm); }

.panel-hd {
  display: flex; align-items: center; gap: 6px;
  padding: 11px 14px 9px;
  border-bottom: 1px solid #F0F2F5;
  font-size: 12px; font-weight: 600; color: #374151;
}
.panel-hd .el-icon { color: var(--primary); font-size: 14px; }
.panel-link { margin-left: auto; font-size: 10px !important; color: #A0AAB8 !important; }
.panel-link:hover { color: var(--primary) !important; }
.panel-hint { margin-left: auto; font-size: 10px; color: #C8CED8; font-weight: 400; }
.panel-bd { padding: 12px 14px; }

.skeleton-text { height: 10px; background: #F0F2F5; border-radius: 4px; animation: fade-pulse 1.6s infinite; margin: 4px 0; }
@keyframes fade-pulse { 0%,100%{opacity:.45} 50%{opacity:.85} }

.empty-mini { font-size: 11px; color: #A0AAB8; text-align: center; padding: 18px 0; }
.empty-mini.safe { color: #60A5FA; }

/* ═══════════ Left — Profile ═══════════ */
.panel-profile .panel-bd { padding-top: 0; position: relative; }

.profile-banner {
  height: 48px; margin: -12px -14px 0;
  background: var(--primary);
  border-radius: 10px 10px 0 0;
}

.profile-avatar-wrap { position: relative; margin-top: -20px; display: flex; justify-content: center; }
.profile-avatar {
  width: 42px; height: 42px; border-radius: 50%;
  background: #EFF6FF;
  color: var(--primary); display: flex; align-items: center; justify-content: center;
  font-size: 17px; font-weight: 700; border: 2.5px solid #fff;
  box-shadow: 0 2px 8px rgba(37,99,235,.15); z-index: 1;
}
.profile-name { text-align: center; font-size: 13px; font-weight: 600; color: #1F2937; margin-top: 6px; }
.profile-tag {
  display: inline-block; margin: 4px auto 0; padding: 2px 9px;
  background: rgba(37,99,235,.07); color: #2563EB; border-radius: 12px;
  font-size: 10px; font-weight: 500; text-align: center;
}
.profile-stats {
  display: flex; justify-content: center; gap: 24px;
  margin-top: 10px; padding-top: 10px;
  border-top: 1px dashed #EBEEF3;
}
.pstat { text-align: center; }
.pstat-val { font-size: 17px; font-weight: 700; color: #1F2937; line-height: 1.2; }
.pstat-label { display: block; font-size: 10px; color: #9CA3AF; margin-top: 1px; }

/* ═══════════ Left — Path ═══════════ */
.path-step {
  display: flex; gap: 9px; align-items: center;
  margin-bottom: 8px; padding: 8px 10px;
  background: #FAFBFC; border-radius: 8px;
  transition: background .15s;
}
.path-step:last-child { margin-bottom: 0; }
.path-step:hover { background: #F4F6FB; }
.path-step-num {
  width: 22px; height: 22px; border-radius: 6px;
  background: #2563EB;
  color: #fff; font-size: 11px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.path-step-info { min-width: 0; }
.path-step-name { font-size: 12px; font-weight: 500; color: #374151; }
.path-step-meta { font-size: 10px; color: #9CA3AF; }

/* ═══════════ Left — Actions ═══════════ */
.actions-list { display: flex; flex-direction: column; gap: 5px; }
.action-btn {
  display: flex; align-items: center; gap: 7px;
  padding: 8px 11px; border-radius: 8px;
  border: 1px solid #E8ECF1;
  background: #FFF; color: #6B7280;
  font-size: 12px; font-weight: 500; cursor: pointer;
  transition: all .15s; width: 100%;
}
.action-btn:hover { border-color: #BFDBFE; color: var(--primary); background: #F8FAFF; }
.action-btn.primary {
  background: var(--primary); color: #fff; border-color: var(--primary);
}
.action-btn.primary:hover { background: #1D4ED8; }
.action-btn .el-icon { font-size: 15px; opacity: .8; }
.action-btn:hover .el-icon { opacity: 1; }

/* ═══════════ Center — Welcome Banner ═══════════ */
.panel-welcome {
  border-color: rgba(37,99,235,.15);
  background: #F0F5FF;
}
.welcome-body { padding: 14px 14px 10px; }
.welcome-subtitle {
  margin: 0 0 14px;
  font-size: 12px; font-weight: 500; color: #6B7280;
}
.welcome-steps { display: flex; flex-direction: column; gap: 6px; }
.welcome-step {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 14px;
  background: #FFFFFF; border: 1px solid #E8ECF1; border-radius: 10px;
  cursor: pointer; transition: all .15s;
}
.welcome-step:hover { border-color: #BFDBFE; background: #FAFCFF; transform: translateX(2px); }
.welcome-step:hover .ws-num { background: var(--primary); }
.ws-num {
  width: 26px; height: 26px; border-radius: 50%;
  background: #2563EB;
  color: #fff;
  font-size: 13px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: background .15s;
}
.ws-info { flex: 1; min-width: 0; }
.ws-title { font-size: 13px; font-weight: 600; color: #1F2937; }
.ws-desc { font-size: 11px; color: #9CA3AF; margin-top: 2px; }
.welcome-step .el-icon { color: #C4CCD6; flex-shrink: 0; }

/* ═══════════ Center — Agent Stats ═══════════ */
.agent-stats-row {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px;
  padding: 2px 0;
}
.agent-stat-chip {
  display: flex; align-items: center; gap: 5px;
  padding: 8px 9px; border-radius: 8px;
  background: #FAFBFC; border: 1px solid #EFF1F4;
  transition: background .15s;
}
.agent-stat-chip:hover { background: #fff; }
.asc-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.asc-dot.green { background: #10B981; box-shadow: 0 0 6px rgba(16,185,129,.3); }
.asc-dot.blue { background: #2563EB; box-shadow: 0 0 6px rgba(37,99,235,.3); }
.asc-dot.orange { background: #F59E0B; box-shadow: 0 0 6px rgba(245,158,11,.3); }
.asc-dot.purple { background: #8B5CF6; box-shadow: 0 0 6px rgba(139,92,246,.3); }
.asc-name { font-size: 10px; font-weight: 500; color: #6B7280; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.asc-count { margin-left: auto; font-size: 12px; font-weight: 600; color: #1F2937; flex-shrink: 0; }

/* ═══════════ Center — Resources ═══════════ */
.resource-mini {
  display: flex; align-items: center; gap: 9px;
  padding: 9px 10px; margin: 0 -14px;
  border-bottom: 1px solid #F5F7FA;
  cursor: pointer; transition: background .15s;
  border-left: 2px solid transparent;
}
.resource-mini:last-child { border-bottom: none; }
.resource-mini:hover { background: #FAFCFF; border-left-color: var(--primary); }

.resource-mini .el-icon {
  width: 32px; height: 32px; border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(37,99,235,.06); flex-shrink: 0;
}
.resource-mini:nth-child(2n) .el-icon { background: rgba(16,185,129,.08); color: #10B981; }
.resource-mini:nth-child(2n+1) .el-icon { background: rgba(139,92,246,.08); color: #8B5CF6; }
.resource-mini-info { flex: 1; min-width: 0; }
.resource-mini-title { font-size: 12px; font-weight: 500; color: #374151; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.resource-mini-type { font-size: 10px; color: #9CA3AF; margin-top: 1px; }
.resource-mini-time { font-size: 10px; color: #C4CCD6; flex-shrink: 0; }

/* ═══════════ Right — BKT ═══════════ */
.bkt-row { display: flex; align-items: center; gap: 8px; margin-bottom: 9px; }
.bkt-row:last-child { margin-bottom: 0; }
.bkt-name { width: 56px; font-size: 10px; font-weight: 500; color: #6B7280; text-align: right; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bkt-bar-wrap { flex: 1; min-width: 0; height: 6px; background: #F0F2F5; border-radius: 3px; overflow: hidden; }
.bkt-bar { height: 100%; border-radius: 3px; transition: width .8s ease; }
.bkt-bar.high { background: #10B981; }
.bkt-bar.mid { background: #2563EB; }
.bkt-bar.low { background: #F59E0B; }
.bkt-pct { width: 30px; font-size: 10px; font-weight: 600; flex-shrink: 0; text-align: right; }

/* ═══════════ Right — Risk ═══════════ */
.risk-row { display: flex; align-items: flex-start; gap: 7px; padding: 7px 0; border-bottom: 1px solid #F5F7FA; }
.risk-row:last-child { border-bottom: none; }
.risk-dot { width: 6px; height: 6px; border-radius: 50%; margin-top: 3px; flex-shrink: 0; }
.risk-row.high .risk-dot { background: #EF4444; box-shadow: 0 0 5px rgba(239,68,68,.4); }
.risk-row.medium .risk-dot { background: #F59E0B; box-shadow: 0 0 5px rgba(245,158,11,.4); }
.risk-row.low .risk-dot { background: #10B981; box-shadow: 0 0 5px rgba(16,185,129,.4); }
.risk-info { display: flex; flex-direction: column; gap: 1px; }
.risk-name { font-size: 11px; font-weight: 500; color: #374151; }
.risk-desc { font-size: 10px; color: #9CA3AF; }

/* 学习风险面板内部滚动 */
.risk-scroll { max-height: 180px; overflow-y: auto; overflow-x: hidden; }

/* BKT掌握率面板内部滚动 */
.bkt-scroll { max-height: 130px; overflow-y: auto; overflow-x: hidden; }

/* ═════════ Right — Radar / KB ═══════════ */
.panel-radar-bd { padding: 8px 10px; }

.kb-stats { display: flex; justify-content: space-around; padding: 4px 0; }
.kb-stat { text-align: center; position: relative; }
.kb-stat:first-child::after { content: ''; position: absolute; right: -28%; top: 12%; width: 1px; height: 55%; background: #E8ECF1; }
.kb-num { font-size: 21px; font-weight: 700; line-height: 1.2; }
.kb-stat:nth-child(1) .kb-num { color: #2563EB; }
.kb-stat:nth-child(2) .kb-num { color: #10B981; }
.kb-stat:nth-child(3) .kb-num { color: #F59E0B; }
.kb-unit { display: block; font-size: 10px; color: #9CA3AF; margin-top: 2px; }

/* ═══════════ Dashboard Error ═══════════ */
.dashboard-error {
  margin: 0 18px;
  flex-shrink: 0;
}

/* ═══════════ Responsive ═══════════ */
@media (max-width: 1200px) {
  .col-right { display: none; }
}

@media (max-width: 768px) {
  .intelligence-center {
    flex-direction: column;
    padding: 10px;
    gap: 10px;
    height: auto;
    min-height: calc(100dvh - var(--header-h));
  }
  .col-left {
    display: flex;
    width: 100%;
    flex-direction: column;
    gap: 10px;
  }
  .col-center {
    width: 100%;
    flex: none;
  }
  .col-right {
    display: flex;
    width: 100%;
    flex-direction: column;
    gap: 10px;
  }
  .agent-stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .action-btn {
    padding: 12px 14px;
    font-size: 13px;
  }
  .panel-profile .panel-bd { padding: 8px 10px 12px; }
  .profile-stats { gap: 32px; }
  .bkt-name { width: 44px; font-size: 10px; }
  .resource-mini {
    padding: 12px 10px;
    margin: 0 -10px;
  }
}

@media (max-width: 480px) {
  .intelligence-center {
    padding: 8px;
    gap: 8px;
  }
  .panel-hd {
    padding: 10px 12px 8px;
  }
  .panel-bd {
    padding: 10px 12px;
  }
  .agent-stats-row {
    grid-template-columns: 1fr 1fr;
    gap: 4px;
  }
  .agent-stat-chip {
    padding: 6px 7px;
  }
}
</style>
