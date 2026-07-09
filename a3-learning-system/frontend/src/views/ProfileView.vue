<template>
  <div class="page">
    <div v-if="loading" class="loading a-fade">
      <el-icon class="spin"><Loading /></el-icon>
      <span>加载中...</span>
    </div>

    <!-- ═══ Error state ═══ -->
    <div v-else-if="loadError" class="error-state a-scale">
      <el-icon :size="40"><WarningFilled /></el-icon>
      <h3>加载失败</h3>
      <p>{{ loadError }}</p>
      <el-button type="primary" @click="loadData">重新加载</el-button>
    </div>

    <template v-else>
      <!-- ═══════════ Profile Header ═══════════ -->
      <div class="profile-header a-slide">
        <div class="ph-avatar">
          <span class="ph-avatar-text">{{ avatarLetter }}</span>
        </div>
        <div class="ph-info">
          <h1 class="ph-name">{{ displayName }}</h1>
          <p class="ph-meta">
            <span class="ph-username">@{{ userStore.userInfo?.username }}</span>
            <span v-if="memberSince" class="ph-divider">|</span>
            <span v-if="memberSince" class="ph-since">{{ memberSince }}</span>
          </p>
        </div>
      </div>

      <!-- ═══════════ Radar Chart ═══════════ -->
      <div v-if="radarReady" class="radar-section a-fade-up">
        <div class="section-head">
          <h2>能力雷达图</h2>
          <p>基于答题记录与学习行为的六维量化评估</p>
        </div>
        <div class="radar-card">
          <div ref="radarRef" class="radar-chart"></div>
          <div v-if="!hasRadarData" class="radar-empty">
            <el-icon :size="40" color="#CBD5E1"><TrendCharts /></el-icon>
            <p>尚未生成评估数据</p>
            <span>完成答题测试后自动生成能力雷达图</span>
          </div>
        </div>
      </div>

      <!-- ═══════════ Dimension Cards ═══════════ -->
      <div class="section-head a-fade-up" style="animation-delay: 0.05s">
        <h2>学习画像维度</h2>
        <p>6 个维度刻画学习特征，AI 据此定制个性化内容</p>
      </div>

      <div class="grid">
        <div
          v-for="(d, i) in dimensions"
          :key="d.key"
          class="dim-card"
          :style="`animation: fadeUp .45s ease both; animation-delay:${i * 70}ms`"
        >
          <div class="dim-bar" :style="{ background: d.color }"></div>
          <div class="dim-body">
            <div class="dim-icon" :style="{ background: d.bg }">
              <el-icon :size="22" :style="{ color: d.color }">
                <component :is="d.icon" />
              </el-icon>
            </div>

            <!-- Display mode -->
            <div v-if="!d.editing" class="dim-content">
              <div class="dim-name">{{ d.label }}</div>

              <div v-if="d.key === 'knowledge_base' && knowledgeEntries.length" class="dim-skill-bars">
                <div v-for="(kv, ki) in knowledgeEntries" :key="ki" class="skill-row">
                  <span class="skill-label">{{ kv.name }}</span>
                  <div class="skill-track">
                    <div class="skill-fill" :style="{ width: kv.score + '%', background: d.color }" />
                  </div>
                  <span class="skill-num">{{ kv.score }}%</span>
                </div>
              </div>

              <div v-else-if="d.key === 'cognitive_style'" class="dim-badge-row">
                <span v-if="styleLabel" class="dim-badge" :style="{ background: d.bg, color: d.color }">
                  <el-icon :size="14"><component :is="styleIcon" /></el-icon>
                  {{ styleLabel }}
                </span>
                <span v-else class="dim-empty">点击编辑填写</span>
              </div>

              <div v-else-if="d.key === 'learning_goal'" class="dim-badge-row">
                <span v-if="goalLabel" class="dim-badge" :style="{ background: d.bg, color: d.color }">
                  <el-icon :size="14"><component :is="goalIcon" /></el-icon>
                  {{ goalLabel }}
                </span>
                <span v-else class="dim-empty">点击编辑填写</span>
              </div>

              <div v-else-if="d.key === 'weekly_hours'" class="dim-hours">
                <span v-if="profileData.weekly_hours != null" class="hours-num">
                  {{ profileData.weekly_hours }}
                </span>
                <span v-else class="dim-empty">点击编辑填写</span>
                <span v-if="profileData.weekly_hours != null" class="hours-unit">小时 / 周</span>
              </div>

              <div v-else-if="d.key === 'preferred_resource_type'" class="dim-badge-row">
                <span v-if="resourceLabel" class="dim-badge" :style="{ background: d.bg, color: d.color }">
                  <el-icon :size="14"><component :is="resourceIcon" /></el-icon>
                  {{ resourceLabel }}
                </span>
                <span v-else class="dim-empty">点击编辑填写</span>
              </div>

              <div v-else-if="d.key === 'error_patterns' && errorPatterns.length" class="dim-errors">
                <div v-for="(ep, ei) in errorPatterns" :key="ei" class="error-item">
                  <el-icon :size="13" color="#EF4444"><WarningFilled /></el-icon>
                  <span class="error-type">{{ errorTypeMap[ep.type] || ep.type }}</span>
                  <span class="error-concepts">{{ ep.concepts?.join('、') }}</span>
                </div>
              </div>

              <div v-else-if="d.key === 'knowledge_base'" class="dim-badges">
                <span
                  v-for="(level, name) in (profileData.knowledge_base || {})"
                  :key="String(name)"
                  class="dim-badge"
                  :style="{ background: d.bg, color: d.color }"
                >
                  {{ name }}
                  <span class="level-dot" :class="`level-${level}`">{{ levelMap[level] || level }}</span>
                </span>
                <span v-if="!profileData.knowledge_base || !Object.keys(profileData.knowledge_base).length" class="dim-empty">
                  暂无数据，开始对话学习后自动更新
                </span>
              </div>

              <div v-else class="dim-val">{{ displayRawVal(d.key) || '点击编辑填写' }}</div>
            </div>

            <!-- Edit mode -->
            <div v-else class="dim-content">
              <div class="dim-name">{{ d.label }}</div>

              <!-- 易错模式: 可视化 chip 编辑器 (业内最佳实践: 不让用户写 JSON) -->
              <ErrorPatternEditor
                v-if="d.key === 'error_patterns'"
                :model-value="editForm.error_patterns"
                field-name="error_patterns"
                @update:model-value="editForm.error_patterns = $event"
                @save="finishEdit(d)"
                @change="() => onFieldChange('error_patterns')"
              />

              <!-- 知识基础: 可视化 chip 编辑器 --><!-- 知识基础: JSON格式编辑 -->
              <div v-else-if="d.key === 'knowledge_base'" class="dim-kb-edit">
                <el-input
                  v-model="editForm.knowledge_base"
                  type="textarea"
                  :rows="3"
                  size="small"
                  placeholder='JSON格式, 如 {\"Python\":80,\"数学\":60}'
                  @blur="() => { markDirty(d.key); finishEdit(d) }"
                />
                <span class="dim-edit-hint">JSON格式: 知识点名称 → 掌握度(0-100)</span>
              </div>

              <el-input
                v-else
                v-model="editForm[d.key]"
                size="small"
                @blur="() => { markDirty(d.key); finishEdit(d) }"
                @keydown.enter="() => { markDirty(d.key); finishEdit(d) }"
              />
            </div>

            <el-button text class="dim-edit-btn" @click="startEdit(d)">
              <el-icon :size="15"><Edit /></el-icon>
            </el-button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import {
  Reading, View, Flag, Timer, Collection, WarningFilled,
  Loading, Edit, TrendCharts, TrophyBase, MagicStick, Suitcase, Star,
  VideoCamera, Document, Monitor, Connection, Headset, Promotion,
} from '@element-plus/icons-vue'
import ErrorPatternEditor from '@/components/ErrorPatternEditor.vue'
import * as echarts from 'echarts'
import { useUserStore } from '@/stores/user'
import type { LearningProfile, ProfileUpdateData } from '@/api/profile'

const userStore = useUserStore()

interface DimDef {
  key: keyof ProfileFields
  label: string
  icon: string
  color: string
  bg: string
  editing: boolean
}

type ProfileFields = Pick<
  LearningProfile,
  'knowledge_base' | 'cognitive_style' | 'learning_goal' |
  'weekly_hours' | 'preferred_resource_type' | 'error_patterns'
>

const dimensions = reactive<DimDef[]>([
  { key: 'knowledge_base',        label: '知识基础', icon: 'Reading',       color: '#2563EB', bg: 'rgba(37,99,235,.10)', editing: false },
  { key: 'cognitive_style',       label: '认知风格', icon: 'View',          color: '#10B981', bg: 'rgba(16,185,129,.10)', editing: false },
  { key: 'learning_goal',         label: '学习目标', icon: 'Flag',          color: '#F59E0B', bg: 'rgba(245,158,11,.10)', editing: false },
  { key: 'weekly_hours',          label: '每周时间', icon: 'Timer',         color: '#8B5CF6', bg: 'rgba(139,92,246,.10)', editing: false },
  { key: 'preferred_resource_type', label: '偏好资源', icon: 'Collection',  color: '#3B82F6', bg: 'rgba(59,130,246,.12)', editing: false },
  { key: 'error_patterns',        label: '易错模式', icon: 'WarningFilled',color: '#EF4444', bg: 'rgba(239,68,68,.08)', editing: false },
])

const loading = ref(true)
const loadError = ref('')
const radarRef = ref<HTMLDivElement | null>(null)
const radarReady = ref(false)
let chartInstance: echarts.ECharts | null = null

const editForm = reactive<Record<string, string>>({
  knowledge_base: '',
  cognitive_style: '',
  learning_goal: '',
  weekly_hours: '',
  preferred_resource_type: '',
  error_patterns: '',
})

// 跟踪哪些字段被用户编辑过 (业内最佳实践: 只 PUT 被修改的字段)
// 用 ref<string[]> 而非 reactive<Set> 是因为 Vue 的 reactive 不支持 Set/Map 泛型
const dirtyFields = ref<string[]>([])

function markDirty(key: string) {
  if (!dirtyFields.value.includes(key)) {
    dirtyFields.value.push(key)
  }
}

function isDirty(key: string): boolean {
  return dirtyFields.value.includes(key)
}

const profileData = computed<LearningProfile>(() => {
  return userStore.profile ?? {
    user_id: 0,
    knowledge_base: null,
    cognitive_style: null,
    learning_goal: null,
    weekly_hours: null,
    error_patterns: null,
    preferred_resource_type: null,
    dimension_scores: null,
  }
})

const avatarLetter = computed(() => {
  const name = userStore.userInfo?.nickname || userStore.userInfo?.username || '?'
  return name.charAt(0).toUpperCase()
})

const displayName = computed(() => {
  return userStore.userInfo?.nickname || userStore.userInfo?.username || '未登录'
})

const memberSince = computed(() => {
  const raw = userStore.userInfo?.created_at
  if (!raw) return ''
  try {
    const d = new Date(raw)
    if (isNaN(d.getTime())) return ''
    return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月加入`
  } catch { return '' }
})

const dimensionScores = computed<Record<string, number> | null>(() => {
  return profileData.value.dimension_scores
})

const hasRadarData = computed(() => {
  const ds = dimensionScores.value
  return ds && Object.keys(ds).length > 0
})

const radarIndicators: Record<string, { label: string; max: number }> = {
  knowledge: { label: '知识储备', max: 100 },
  logic: { label: '逻辑能力', max: 100 },
  practice: { label: '实践能力', max: 100 },
  speed: { label: '学习速度', max: 100 },
  focus: { label: '专注度', max: 100 },
  overall: { label: '综合水平', max: 100 },
}

const knowledgeEntries = computed(() => {
  const kbRaw: unknown = profileData.value.knowledge_base
  if (!kbRaw) return []
  // 兼容后端 MySQL JSON 列可能返回 JSON 字符串的情况
  let kb: Record<string, number>
  if (typeof kbRaw === 'string') {
    try { kb = JSON.parse(kbRaw) } catch { return [] }
  } else if (typeof kbRaw === 'object' && kbRaw !== null) {
    kb = kbRaw as Record<string, number>
  } else {
    return []
  }
  return Object.entries(kb)
    .filter(([, score]) => typeof score === 'number' && !isNaN(score))
    .map(([name, score]) => ({
      name,
      score: Math.min(100, Math.max(0, Math.round(score))),
    }))
})

const styleMap: Record<string, { label: string; icon: string }> = {
  visual: { label: '视觉型', icon: 'View' },
  auditory: { label: '听觉型', icon: 'Headset' },
  kinesthetic: { label: '动觉型', icon: 'Promotion' },
  reading: { label: '阅读型', icon: 'Reading' },
}
function normalizeStyle(raw: string | null | undefined): string {
  if (!raw) return ''
  const map: Record<string,string> = { visual: '视觉型', auditory: '听觉型', kinesthetic: '动手型', reading: '阅读型' }
  if (map[raw]) return map[raw]
  if (/写代码|动手|敲|做项目|实践|操作|kinesthetic|hands.on/i.test(raw)) return '动手型'
  if (/看|读|视觉|图|视频|visual|watch/i.test(raw)) return '视觉型'
  if (/听|音频|auditory|listen/i.test(raw)) return '听觉型'
  return raw
}
const styleLabel = computed(() => normalizeStyle(profileData.value.cognitive_style))
const styleIcon = computed(() => styleMap[profileData.value.cognitive_style ?? '']?.icon ?? 'View')

const goalMap: Record<string, { label: string; icon: string }> = {
  exam: { label: '考试备考', icon: 'TrophyBase' },
  skill: { label: '技能提升', icon: 'MagicStick' },
  career: { label: '职业发展', icon: 'Suitcase' },
  interest: { label: '兴趣探索', icon: 'Star' },
}
const goalLabel = computed(() => goalMap[profileData.value.learning_goal ?? '']?.label ?? profileData.value.learning_goal)
const goalIcon = computed(() => goalMap[profileData.value.learning_goal ?? '']?.icon ?? 'Flag')

const resourceMap: Record<string, { label: string; icon: string }> = {
  video: { label: '视频', icon: 'VideoCamera' },
  text: { label: '文档', icon: 'Document' },
  code: { label: '代码', icon: 'Monitor' },
  interactive: { label: '互动', icon: 'Connection' },
}
const resourceLabel = computed(() => resourceMap[profileData.value.preferred_resource_type ?? '']?.label ?? profileData.value.preferred_resource_type)
const resourceIcon = computed(() => resourceMap[profileData.value.preferred_resource_type ?? '']?.icon ?? 'Collection')

const errorPatterns = computed(() => {
  const ep = profileData.value.error_patterns
  if (!ep || !Array.isArray(ep)) return []
  return ep as Array<{ type: string; concepts: string[] }>
})
const errorTypeMap: Record<string, string> = {
  confusion: '概念混淆',
  forgetting: '知识点遗忘',
  carelessness: '粗心大意',
  misunderstanding: '理解偏差',
  application: '应用困难',
}
// 知识点熟练度 (业内最佳实践: 用户友好的中文标签)
const levelMap: Record<string, string> = {
  beginner: '入门',
  intermediate: '掌握',
  advanced: '熟练',
  expert: '精通',
}

function isComplexDim(key: string): boolean {
  return key === 'knowledge_base' || key === 'error_patterns'
}

function startEdit(dim: DimDef) {
  dim.editing = true
}

function finishEdit(dim: DimDef) {
  dim.editing = false
  save()
}

function displayRawVal(key: string): string {
  const raw = editForm[key]
  if (!raw) return ''
  try {
    const parsed = JSON.parse(raw)
    return typeof parsed === 'object' ? JSON.stringify(parsed) : String(parsed)
  } catch {
    return String(raw)
  }
}

async function loadData() {
  loading.value = true
  loadError.value = ''
  try {
    await Promise.all([
      userStore.fetchUserInfo(),
      userStore.fetchProfile(),
    ])
    syncEditForm()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    loadError.value = err?.response?.data?.detail || err?.message || '加载失败，请检查网络连接'
  } finally {
    loading.value = false
    await nextTick()
    initRadarChart()
  }
}

function syncEditForm() {
  const p = profileData.value
  for (const dim of dimensions) {
    const val = p[dim.key]
    if (val !== null && val !== undefined) {
      editForm[dim.key] = typeof val === 'object' ? JSON.stringify(val) : String(val)
    } else {
      editForm[dim.key] = ''
    }
  }
}

const saving = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null

/**
 * 业内最佳实践 (参考 Notion / Linear / Anki):
 *   - 用户每次操作触发 @change 事件
 *   - 1.5s 内无新操作 → 自动写入后端 (auto-save)
 *   - 比"必须点保存按钮"更符合用户预期，避免数据丢失
 */
function autoSaveDebounced() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(save, 1500)
}

// 字段被改动时调用 (子组件 @change 触发)
function onFieldChange(field: string) {
  markDirty(field)
  autoSaveDebounced()
}

async function save() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  // 关键修复: 只发被用户编辑过的字段 (业内最佳实践)
  if (dirtyFields.value.length === 0) {
    console.log('[ProfileView] 没有 dirty 字段，跳过保存')
    return
  }
  const body: ProfileUpdateData = {}
  for (const key of dirtyFields.value) {
    const raw = editForm[key]
    if (key === 'error_patterns' || key === 'knowledge_base') {
      if (raw === '' || raw === undefined) {
        ;(body as Record<string, unknown>)[key] = null
        continue
      }
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed) && parsed.length === 0) {
          ;(body as Record<string, unknown>)[key] = null
        } else if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && Object.keys(parsed).length === 0) {
          ;(body as Record<string, unknown>)[key] = null
        } else {
          ;(body as Record<string, unknown>)[key] = parsed
        }
      } catch (e) {
        console.error('[ProfileView] JSON parse failed for', key, raw, e)
        ;(body as Record<string, unknown>)[key] = null
      }
    } else if (key === 'weekly_hours') {
      // 数字字段: 转 number 或 null
      if (raw === '' || raw === undefined || raw === null) {
        ;(body as Record<string, unknown>)[key] = null
      } else {
        const num = Number(raw)
        ;(body as Record<string, unknown>)[key] = isNaN(num) ? null : num
      }
    } else {
      ;(body as Record<string, unknown>)[key] = raw === '' ? null : raw
    }
  }
  console.log('[ProfileView] auto-saving profile...', body)
  saving.value = true
  try {
    const updated = await userStore.updateProfile(body)
    console.log('[ProfileView] save success, updated profile:', updated)
    ElNotification({
      title: '已保存',
      message: `更新了 ${Object.keys(body).length} 个字段: ${Object.keys(body).join(', ')}`,
      type: 'success',
      duration: 2000,
      position: 'top-right',
    })
    // 重新同步 editForm（确保与后端一致）+ 清空 dirty 标记
    syncEditForm()
    dirtyFields.value = []
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    const msg = err?.response?.data?.detail || err?.message || String(e)
    console.error('[ProfileView] save failed:', e)
    ElNotification({
      title: '保存失败',
      message: msg,
      duration: 5000,
      position: 'top-right',
    })
  } finally {
    saving.value = false
  }
}

function initRadarChart() {
  if (!radarRef.value) return
  radarReady.value = true

  const ds = dimensionScores.value
  if (!ds || Object.keys(ds).length === 0) return

  // 维度标签映射表（中文友好名称）
  const dimensionLabelMap: Record<string, string> = {
    knowledge: '知识储备', logic: '逻辑能力', practice: '实践能力',
    speed: '学习速度', focus: '专注度', overall: '综合水平',
  }
  const indicators: Array<{ name: string; max: number }> = []
  const dataValues: number[] = []
  // 读取 API 返回的实际维度键，映射中文标签
  for (const [key, val] of Object.entries(ds)) {
    const label = dimensionLabelMap[key] || key
    indicators.push({ name: label, max: 100 })
    dataValues.push(val as number)
  }

  chartInstance = echarts.init(radarRef.value)
  chartInstance.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: '#FFFFFF',
      borderColor: '#E2E8F0',
      textStyle: { color: '#0F172A', fontSize: 13 },
    },
    legend: {
      bottom: 0,
      data: ['当前水平'],
      textStyle: { color: '#64748B', fontSize: 12 },
      itemWidth: 10, itemHeight: 10, itemGap: 20,
    },
    radar: {
      center: ['50%', '48%'],
      radius: '62%',
      indicator: indicators,
      axisName: { color: '#64748B', fontSize: 12 },
      shape: 'polygon',
      splitNumber: 5,
      axisLine: { lineStyle: { color: '#E2E8F0' } },
      splitLine: { lineStyle: { color: '#E2E8F0' } },
      splitArea: {
        areaStyle: {
          color: [
            'rgba(37,99,235,.03)',
            'rgba(16,185,129,.04)',
            'rgba(245,158,11,.05)',
            'rgba(139,92,246,.06)',
            'rgba(37,99,235,.08)',
          ],
        },
      },
    },
    series: [{
      name: '当前水平',
      type: 'radar',
      data: [{
        value: dataValues,
        name: '当前水平',
        areaStyle: { color: 'rgba(37,99,235,.18)' },
        lineStyle: { color: '#2563EB', width: 2.5 },
        itemStyle: { color: '#2563EB', borderColor: '#FFFFFF', borderWidth: 2 },
      }],
      symbol: 'circle',
      symbolSize: 6,
    }],
  })
}

function handleResize() {
  chartInstance?.resize()
}

onMounted(() => {
  loadData()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (saveTimer) clearTimeout(saveTimer)
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
})
</script>

<style scoped>
/* ═══════════ Page ═══════════ */
.page {
  max-width: 1040px;
  margin: 0 auto;
  padding: 32px 28px 48px;
}
.loading {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: center;
  padding: 100px 0;
  color: var(--text-secondary);
  font-size: var(--font-base);
}
.spin { animation: spin 1s linear infinite; }

/* ═══ Error State ═══ */
.error-state {
  text-align: center;
  padding: 80px 0;
}
.error-state .el-icon {
  color: var(--red, #EF4444);
  margin-bottom: 16px;
}
.error-state h3 {
  font-size: var(--font-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}
.error-state p {
  font-size: var(--font-sm);
  color: var(--text-muted);
  margin-bottom: 20px;
  max-width: 360px;
  margin-left: auto;
  margin-right: auto;
}

/* ═══════════ Profile Header ═══════════ */
.profile-header {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 28px;
  padding: 24px 28px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}
.ph-avatar {
  width: 64px; height: 64px;
  border-radius: 50%;
  background: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.ph-avatar-text {
  color: #fff;
  font-size: var(--font-3xl);
  font-weight: 700;
}
.ph-info { min-width: 0; }
.ph-name { font-size: var(--font-2xl); font-weight: 700; color: var(--text-primary); }
.ph-meta { display: flex; align-items: center; gap: 8px; margin-top: 4px; font-size: var(--font-sm); color: var(--text-secondary); }
.ph-divider { color: var(--border); }

/* ═══════════ Section Head ═══════════ */
.section-head { margin-bottom: 18px; }
.section-head h2 { font-size: var(--font-xl); font-weight: 700; color: var(--text-primary); }
.section-head p { font-size: var(--font-sm); color: var(--text-secondary); margin-top: 4px; }

/* ═══════════ Radar ═══════════ */
.radar-section { margin-bottom: 32px; }
.radar-card {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 8px 0 16px;
}
.radar-chart { width: 100%; height: 360px; }
.radar-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  pointer-events: none;
}
.radar-empty p { font-size: var(--font-lg); font-weight: 600; color: var(--text-muted); }
.radar-empty span { font-size: var(--font-sm); color: var(--text-muted); }

/* ═══════════ Dimension Cards ═══════════ */
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.dim-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: border-color var(--transition-fast);
}
.dim-card:hover {
  border-color: var(--border);
}
.dim-bar { height: 3px; }
.dim-body { display: flex; align-items: flex-start; gap: 14px; padding: 20px; }
.dim-icon {
  width: 46px; height: 46px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.dim-content { flex: 1; min-width: 0; }
.dim-name { font-size: var(--font-base); font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.dim-val { font-size: var(--font-sm); color: var(--text-secondary); line-height: 1.5; }
.dim-empty { font-size: var(--font-sm); color: var(--text-muted); font-style: italic; }
.dim-edit-btn { flex-shrink: 0; color: var(--text-muted); margin-top: 2px; transition: color var(--transition-fast); }
.dim-edit-btn:hover { color: var(--primary); }
.dim-edit-hint { margin-top: 4px; font-size: var(--font-xs); color: var(--text-muted); }

/* Skill bars */
.dim-skill-bars { display: flex; flex-direction: column; gap: 8px; }
.skill-row { display: flex; align-items: center; gap: 8px; }
.skill-label { width: 64px; font-size: var(--font-xs); color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-shrink: 0; }
.skill-track { flex: 1; height: 6px; background: var(--bg-muted); border-radius: var(--radius-sm); overflow: hidden; }
.skill-fill { height: 100%; border-radius: var(--radius-sm); transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1); }
.skill-num { width: 32px; font-size: var(--font-xs); color: var(--text-muted); text-align: right; flex-shrink: 0; }

/* Badges */
.dim-badge-row { display: flex; align-items: center; gap: 4px; }
.dim-badge { display: inline-flex; align-items: center; gap: 5px; padding: 4px 12px; border-radius: var(--radius-xl); font-size: var(--font-xs); font-weight: 600; border: 1px solid; border-color: inherit; }

/* Hours */
.dim-hours { display: flex; align-items: baseline; gap: 4px; }
.hours-num { font-size: 22px; font-weight: 700; color: var(--purple); line-height: 1; }
.hours-unit { font-size: var(--font-sm); color: var(--text-secondary); }

/* Error patterns */
.dim-errors { display: flex; flex-direction: column; gap: 6px; }
.error-item { display: flex; align-items: flex-start; gap: 5px; font-size: var(--font-xs); line-height: 1.4; }
.error-type { font-weight: 600; color: var(--red); white-space: nowrap; }
.error-concepts { color: var(--text-secondary); word-break: break-all; }

/* ═══════════ Responsive ═══════════ */
@media (max-width: 768px) {
  .page { padding: 20px 16px 36px; }
  .profile-header { flex-direction: column; text-align: center; padding: 20px; gap: 12px; }
  .ph-avatar { width: 52px; height: 52px; }
  .ph-avatar-text { font-size: 20px; }
  .ph-name { font-size: 18px; }
  .grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .radar-chart { height: 280px; }
}

@media (max-width: 480px) {
  .page { padding: 12px 10px 28px; }
  .profile-header { padding: 16px; gap: 8px; }
  .ph-avatar { width: 44px; height: 44px; }
  .section-head h2 { font-size: 16px; }
  .section-head p { font-size: 11px; }
  .grid { grid-template-columns: 1fr; gap: 8px; }
  .dim-body { padding: 14px; gap: 10px; }
  .dim-icon { width: 38px; height: 38px; }
  .dim-name { font-size: 13px; margin-bottom: 4px; }
  .radar-chart { height: 240px; }
  .skill-label { width: 50px; font-size: 10px; }
  .hours-num { font-size: 18px; }
  .el-input__inner { font-size: 12px !important; }
}
</style>
