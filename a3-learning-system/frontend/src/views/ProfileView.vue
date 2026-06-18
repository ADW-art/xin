<template>
  <div class="page">
    <div v-if="loading" class="loading a-fade">
      <el-icon class="spin"><Loading /></el-icon>
      <span>加载中...</span>
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

              <div v-else class="dim-val">{{ displayRawVal(d.key) || '点击编辑填写' }}</div>
            </div>

            <!-- Edit mode -->
            <div v-else class="dim-content">
              <div class="dim-name">{{ d.label }}</div>
              <el-input
                v-if="isComplexDim(d.key)"
                v-model="editForm[d.key]"
                type="textarea"
                :rows="3"
                size="small"
                @blur="finishEdit(d)"
                @keydown.escape="d.editing = false"
              />
              <el-input
                v-else
                v-model="editForm[d.key]"
                size="small"
                @blur="finishEdit(d)"
                @keydown.enter="finishEdit(d)"
              />
              <p class="dim-edit-hint" v-if="isComplexDim(d.key)">JSON 格式，点击外部区域保存</p>
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
import { ElMessage } from 'element-plus'
import {
  Reading, View, Flag, Timer, Collection, WarningFilled,
  Loading, Edit, TrendCharts, TrophyBase, MagicStick, Suitcase, Star,
  VideoCamera, Document, Monitor, Connection, Headset, Promotion,
} from '@element-plus/icons-vue'
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
  const kb = profileData.value.knowledge_base
  if (!kb) return []
  return Object.entries(kb).map(([name, score]) => ({
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
const styleLabel = computed(() => styleMap[profileData.value.cognitive_style ?? '']?.label ?? profileData.value.cognitive_style)
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
  try {
    await Promise.all([
      userStore.fetchUserInfo(),
      userStore.fetchProfile(),
    ])
    syncEditForm()
  } catch {
    ElMessage.warning('加载失败，请检查网络连接')
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

async function save() {
  // 300ms debounce: 连续触发只执行最后一次
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    const body: ProfileUpdateData = {}
    for (const dim of dimensions) {
      const raw = editForm[dim.key]
      if (!raw) continue
      try {
        ;(body as Record<string, unknown>)[dim.key] = JSON.parse(raw)
      } catch {
        ;(body as Record<string, unknown>)[dim.key] = raw
      }
    }
    saving.value = true
    try {
      await userStore.updateProfile(body)
      ElMessage.success('保存成功')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      ElMessage.error('保存失败: ' + msg)
    } finally {
      saving.value = false
    }
  }, 300)
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
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 1, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(37,99,235,.25)' },
              { offset: 0.4, color: 'rgba(16,185,129,.20)' },
              { offset: 0.7, color: 'rgba(245,158,11,.15)' },
              { offset: 1, color: 'rgba(139,92,246,.22)' },
            ],
          },
        },
        lineStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 1, y2: 0,
            colorStops: [
              { offset: 0, color: '#2563EB' },
              { offset: 0.5, color: '#10B981' },
              { offset: 1, color: '#8B5CF6' },
            ],
          },
          width: 2.5,
        },
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
</style>
