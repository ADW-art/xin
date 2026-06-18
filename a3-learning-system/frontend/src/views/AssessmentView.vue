<template>
  <div class="page">
    <div class="hero a-slide"><h1>学习评估</h1><p>多维评估 + BKT追踪 + 答题记录</p></div>

    <!-- ═══════ Loading ═══════ -->
    <div v-if="loading" class="loading a-fade"><el-icon class="spin"><Loading/></el-icon></div>

    <!-- ═══════ Error ═══════ -->
    <div v-else-if="errorMsg" class="error a-scale" style="text-align:center;padding:60px 0">
      <el-icon :size="32" color="#EF4444"><WarningFilled/></el-icon>
      <h3 style="margin-top:12px">{{ errorMsg }}</h3>
      <el-button type="primary" @click="loading=true;errorMsg='';fetchData()" style="margin-top:16px">重试</el-button>
    </div>

    <!-- ═══════ Empty ═══════ -->
    <div v-else-if="!hasData" class="empty a-scale">
      <svg viewBox="0 0 200 130" class="e-svg">
        <rect x="30" y="15" width="60" height="8" rx="4" fill="rgba(37,99,235,.18)"/>
        <circle cx="130" cy="50" r="32" fill="rgba(37,99,235,.04)" stroke="rgba(37,99,235,.15)" stroke-width="2"/>
        <circle cx="130" cy="50" r="14" fill="rgba(37,99,235,.10)"/>
        <rect x="40" y="72" width="100" height="6" rx="3" fill="rgba(255,255,255,.04)"/>
        <rect x="40" y="72" width="60" height="6" rx="3" fill="rgba(37,99,235,.15)"/>
      </svg>
      <h3>暂无评估报告</h3><p>对话中说"评估一下我的学习"来生成第一份报告</p>
      <el-button type="primary" @click="$router.push('/chat')">前往对话</el-button>
    </div>

    <!-- ═══════ Data ═══════ -->
    <template v-else>
      <!-- 6维环形图 -->
      <div class="scores a-fade-up">
        <div v-for="s in allScores" :key="s.label" class="score-card">
          <svg viewBox="0 0 90 90" width="72">
            <circle cx="45" cy="45" r="38" fill="none" stroke="#F1F5F9" stroke-width="5"/>
            <circle cx="45" cy="45" r="38" fill="none" :stroke="s.color" stroke-width="5" stroke-linecap="round"
              :stroke-dasharray="2*Math.PI*38" :stroke-dashoffset="2*Math.PI*38*(1-s.val/100)"
              transform="rotate(-90 45 45)"
              style="transition:stroke-dashoffset 1.2s cubic-bezier(.22,.61,.36,1)"/>
            <text x="45" y="48" text-anchor="middle" :fill="s.color" font-size="17" font-weight="700">{{ s.val }}</text>
          </svg>
          <span class="sl">{{ s.label }}</span>
        </div>
      </div>

      <!-- BKT Skills Table -->
      <div v-if="bktConcepts.length > 0" class="card a-fade-up" style="animation-delay:100ms">
        <h3>BKT 知识追踪状态</h3>
        <div class="bkt-grid">
          <div v-for="c in bktConcepts" :key="c.name" class="bkt-row">
            <span class="bkt-name">{{ c.name }}</span>
            <div class="bkt-bar-wrap">
              <div class="bkt-bar" :class="c.levelClass"
                :style="{width: (c.p_known*100)+'%'}">{{ (c.p_known*100).toFixed(0) }}%</div>
            </div>
            <span class="bkt-level" :class="c.levelClass">{{ c.level }}</span>
          </div>
        </div>
      </div>

      <!-- Recent Answer Records -->
      <div v-if="records.length > 0" class="card a-fade-up" style="animation-delay:200ms">
        <h3>最近答题记录</h3>
        <el-table :data="records" stripe size="small" style="width:100%">
          <el-table-column prop="concept" label="知识点" width="150"/>
          <el-table-column prop="is_correct" label="结果" width="80">
            <template #default="{row}">
              <el-tag :type="row.is_correct ? 'success' : 'danger'" size="small">{{ row.is_correct ? '✓' : '✗' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="time_spent" label="耗时(s)" width="80"/>
          <el-table-column prop="created_at" label="时间" width="160">
            <template #default="{row}">{{ (row.created_at||'').slice(0,16).replace('T',' ') }}</template>
          </el-table-column>
          <el-table-column prop="user_answer" label="答案" min-width="120">
            <template #default="{row}">{{ (row.user_answer||'').slice(0,60) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <!-- Report Content -->
      <div class="card a-fade-up" style="animation-delay:300ms">
        <div class="report" v-html="reportHtml"/>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import api from '@/api/index'

const loading = ref(true)
const errorMsg = ref('')
const hasData = ref(false)
const reportContent = ref('')
const reportHtml = computed(() => DOMPurify.sanitize(marked.parse(reportContent.value || '') as string))
interface AnswerRecordDisplay { id?: number; question_id?: number; user_answer?: string; is_correct?: boolean; time_spent?: number; created_at?: string; concept?: string }
interface BktConcept { name: string; p_known: number; level: string; levelClass: string }

const records = ref<AnswerRecordDisplay[]>([])
const bktConcepts = ref<BktConcept[]>([])

const allScores = ref([
  { label: '知识掌握', val: 0, color: '#2563EB' },
  { label: '学习速度', val: 0, color: '#3B82F6' },
  { label: '实践能力', val: 0, color: '#0EA5E9' },
  { label: '专注度', val: 0, color: '#6366F1' },
  { label: '逻辑思维', val: 0, color: '#1D4ED8' },
  { label: '综合评估', val: 0, color: '#60A5FA' },
])

function mapScores(ds: Record<string, unknown> | null | undefined) {
  if (!ds || typeof ds !== 'object') return
  const d = ds as Record<string, number>
  allScores.value = [
    { label: '知识掌握', val: Number(d.knowledge) || 0, color: '#2563EB' },
    { label: '学习速度', val: Number(d.speed) || 0, color: '#3B82F6' },
    { label: '实践能力', val: Number(d.practice) || 0, color: '#0EA5E9' },
    { label: '专注度', val: Number(d.focus) || 0, color: '#6366F1' },
    { label: '逻辑思维', val: Number(d.logic) || 0, color: '#1D4ED8' },
    { label: '综合评估', val: Number(d.overall) || 0, color: '#60A5FA' },
  ]
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

async function fetchData() {
  try {
    const [reportRes, profileRes, bktRes, recordsRes] = await Promise.all([
      api.get('/assessment/reports'),
      api.get('/profile/me'),
      api.get('/bkt/status'),
      api.get('/assessment/records'),
    ])

    const reports = reportRes.data
    const bktData = bktRes.data
    const recordsData = recordsRes.data

    // BKT concepts
    if (bktData?.concepts && bktData.concepts.length > 0) {
      bktConcepts.value = bktData.concepts.map((c: { name: string; p_known?: number }) => ({
        name: c.name,
        p_known: c.p_known || 0,
        level: levelName(c.p_known || 0),
        levelClass: levelClass(c.p_known || 0),
      }))
    }

    // Answer records
    if (Array.isArray(recordsData) && recordsData.length > 0) {
      records.value = recordsData.slice(0, 10)
    } else if (recordsData?.items) {
      records.value = recordsData.items.slice(0, 10)
    }

    // Dimension scores
    if (bktData?.total_concepts > 0 || bktConcepts.value.length > 0) {
      hasData.value = true
    }

    if (reports && reports.length > 0) {
      hasData.value = true
      const r = reports[0]
      reportContent.value = typeof r.report_data === 'object'
        ? r.report_data?.content || ''
        : String(r.report_data || '')

      if (r.dimension_scores && Object.keys(r.dimension_scores).length > 0) {
        mapScores(r.dimension_scores)
      }
    }

    // Fallback to profile scores
    if (allScores.value.every(s => s.val === 0)) {
      const profileDs = profileRes.data?.dimension_scores
      if (profileDs && Object.keys(profileDs).length > 0) {
        mapScores(profileDs)
        if (bktConcepts.value.length === 0) hasData.value = true
      }
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    errorMsg.value = err?.response?.data?.detail || err?.message || '加载评估数据失败，请检查网络连接后重试'
  } finally { loading.value = false }
}
onMounted(fetchData)
</script>

<style scoped>
.page { max-width: 920px; margin: 0 auto; padding: 32px 28px 48px; }
.hero { margin-bottom: 24px; }
.hero h1 { font-size: var(--font-3xl); font-weight: 700; color: var(--text-primary); }
.hero p { font-size: var(--font-base); color: var(--text-secondary); margin-top: 4px; }
.loading { display: flex; justify-content: center; padding: 80px 0; color: var(--text-secondary); }
.spin { animation: spin 1s linear infinite; }
.empty { text-align: center; padding: 60px 0; }
.e-svg { width: 200px; height: 130px; margin-bottom: 16px; opacity: 0.6; }
.empty h3 { font-size: var(--font-lg); font-weight: 600; color: var(--text-primary); }
.empty p { font-size: var(--font-base); color: var(--text-secondary); margin: 4px 0 16px; }

.scores { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 20px; }
@media (min-width: 700px) { .scores { grid-template-columns: repeat(6, 1fr); } }
.score-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px 12px 16px; text-align: center; }
.sl { display: block; font-size: var(--font-xs); color: var(--text-secondary); margin-top: 6px; font-weight: 500; }

.card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 24px; margin-bottom: 18px; }
.card h3 { font-size: var(--font-lg); font-weight: 600; color: var(--text-primary); margin-bottom: 16px; }

.bkt-grid { display: flex; flex-direction: column; gap: 8px; }
.bkt-row { display: flex; align-items: center; gap: 10px; }
.bkt-name { width: 100px; font-size: var(--font-sm); color: var(--text-primary); text-align: right; flex-shrink: 0; }
.bkt-bar-wrap { flex: 1; background: #F1F5F9; border-radius: 4px; height: 22px; overflow: hidden; }
.bkt-bar { height: 100%; border-radius: 4px; color: #fff; font-size: 11px; font-weight: 600; text-align: right; padding-right: 6px; line-height: 22px; transition: width 0.8s ease; min-width: 30px; }
.bkt-bar.mastered { background: #1D4ED8; }
.bkt-bar.learning { background: #2563EB; }
.bkt-bar.familiar { background: #60A5FA; }
.bkt-bar.beginner { background: #93C5FD; }
.bkt-level { width: 50px; font-size: var(--font-xs); text-align: left; flex-shrink: 0; }
.bkt-level.mastered { color: #1D4ED8; }
.bkt-level.learning { color: #2563EB; }
.bkt-level.familiar { color: #60A5FA; }
.bkt-level.beginner { color: #93C5FD; }

.report { line-height: 1.8; }
.report :deep(h3) { margin: 20px 0 10px; color: var(--text-primary); }
.report :deep(pre) { background: #1E293B; color: #E2E8F0; border-radius: var(--radius-md); padding: 16px; border: 1px solid #334155; overflow-x: auto; }
</style>
