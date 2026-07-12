<template>
  <div class="bkt">
    <!-- ═══ Header (RAG-style) ═══ -->
    <div class="bkt-bar">
      <div class="bkt-bar-l">
        <h1>BKT 知识追踪中心</h1>
        <p>基于<strong>贝叶斯四参数模型</strong>的知识状态推断 — Corbett & Anderson 1995</p>
      </div>
      <div class="bkt-bar-r">
        <el-button :type="showDemo ? 'warning' : 'default'" @click="toggleDemo" size="default">
          {{ showDemo ? '停止演示' : '答题演示' }}
        </el-button>
        <el-button type="primary" @click="triggerEmFit" :loading="emFitting" :disabled="totalConcepts === 0" size="default">
          EM 拟合参数
        </el-button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="bkt-loading">
      <el-icon class="spin" :size="32"><Loading /></el-icon>
      <p>加载知识追踪数据...</p>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="bkt-empty">
      <el-icon :size="36" color="#CBD5E1"><WarningFilled /></el-icon>
      <p>{{ error }}</p>
      <el-button type="primary" @click="loadBktData">重新加载</el-button>
    </div>

    <!-- Main Body -->
    <div v-else class="bkt-body">
      <!-- Stats Row (compact) -->
      <div class="bkt-stats">
        <div class="bs-item">
          <span class="bs-v">{{ totalConcepts }}</span><span class="bs-l">知识点</span>
        </div>
        <div class="bs-item">
          <span class="bs-v">{{ (avgMastery * 100).toFixed(0) }}%</span><span class="bs-l">平均掌握</span>
        </div>
        <div class="bs-item">
          <span class="bs-v">{{ totalAttempts }}</span><span class="bs-l">总答题</span>
        </div>
        <div class="bs-item">
          <span class="bs-v">{{ masteredCount }}</span><span class="bs-l">已精通</span>
        </div>
        <div class="bs-item">
          <span class="bs-v">{{ weakCount }}</span><span class="bs-l">待加强</span>
        </div>
      </div>

      <div class="bkt-main">
        <!-- Left: Concept List (compact) -->
        <div class="bkt-left">
          <div class="bkt-card">
            <div class="bc-hd">知识点掌握率</div>
            <div class="bc-bd">
              <div v-for="(item, idx) in masteryList.slice(0, 10)" :key="item.name"
                   class="concept-row"
                   :class="{ active: selectedConcept?.name === item.name, prior: item.attempts === 0 }"
                   @click="selectConcept(item)">
                <div class="cr-info">
                  <span class="cr-name">{{ item.name }}</span>
                  <span class="cr-pct">{{ (item.pKnown * 100).toFixed(0) }}%</span>
                </div>
                <div class="cr-bar-wrap">
                  <div class="cr-bar"
                     :style="{ width: (item.pKnown * 100) + '%', background: ragColor(idx) }" />
                </div>
                <div class="cr-meta">
                  <span class="cr-tag" :class="lvlClass(item.pKnown)">{{ lvlLabel(item.pKnown) }}</span>
                  <span class="cr-n">{{ item.attempts || 0 }}次</span>
                  <span v-if="item.paramSource === 'em_fitted'" class="cr-badge em">EM</span>
                </div>
              </div>
              <div v-if="masteryList.length > 10" class="cr-more">
                还有 {{ masteryList.length - 10 }} 个...
              </div>
            </div>
          </div>

          <!-- Parameters + EM (merged) -->
          <div class="bkt-card">
            <div class="bc-hd">模型参数</div>
            <div class="bc-bd">
              <div class="params-grid">
                <div class="pp-cell">
                  <span class="pp-k">P(L₀)</span>
                  <span class="pp-v">{{ liveParams.pInitial }}</span>
                  <span class="pp-d">初始概率</span>
                </div>
                <div class="pp-cell">
                  <span class="pp-k">P(T)</span>
                  <span class="pp-v">{{ liveParams.pLearn }}</span>
                  <span class="pp-d">学习转移</span>
                </div>
                <div class="pp-cell">
                  <span class="pp-k">P(G)</span>
                  <span class="pp-v">{{ liveParams.pGuess }}</span>
                  <span class="pp-d">猜测率</span>
                </div>
                <div class="pp-cell">
                  <span class="pp-k">P(S)</span>
                  <span class="pp-v">{{ liveParams.pSlip }}</span>
                  <span class="pp-d">失误率</span>
                </div>
              </div>
              <div v-if="emFitResults.length > 0" class="em-compact">
                <div class="em-title">EM拟合 <span class="em-cnt">{{ emFitResults.length }}项</span></div>
                <div v-for="r in emFitResults.slice(0, 3)" :key="r.concept" class="em-row">
                  <span class="em-n">{{ r.concept }}</span>
                  <span class="em-p">L={{ r.params?.p_learn?.toFixed(2) }}</span>
                  <span class="em-r" :class="rmseCls(r.rmse)">{{ r.rmse?.toFixed(3) }}</span>
                </div>
              </div>
              <div v-if="metrics.total_predictions > 0" class="metrics-inline">
                <span>RMSE: <strong :class="rmseCls(metrics.rmse)">{{ metrics.rmse }}</strong></span>
                <span>预测: <strong>{{ metrics.total_predictions }}</strong>次</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Right: Curve + Formula + Demo -->
        <div class="bkt-right">
          <!-- Learning Curve (HERO - larger) -->
          <div class="bkt-card card-hero">
            <div class="bc-hd">
              掌握概率变化曲线
              <template v-if="selectedConcept">
                <span class="chart-sub">— {{ selectedConcept.name }}</span>
              </template>
              <span class="mode-badge" :class="hasRealHistory ? 'real' : 'sim'">
                {{ hasRealHistory ? '真实数据' : '前向模拟' }}
              </span>
            </div>
            <div class="chart-area" ref="lineRef" />
          </div>

          <!-- Bayesian Formula + Live Calc -->
          <div class="bkt-card card-formula">
            <div class="bc-hd">贝叶斯更新规则</div>
            <div class="formula-body">
              <div class="f-row">
                <div class="f-card f-correct">
                  <div class="f-title">答对时 P(k|correct)</div>
                  <div class="f-eq">
                    <span class="f-frac">
                      <span class="f-num">K·(1−S)</span>
                      <span class="f-den">K·(1−S) + (1−K)·G</span>
                    </span>
                  </div>
                  <div class="f-res ok">
                    → {{ (liveCorrectResult * 100).toFixed(1) }}%
                    <span class="f-arrow">→</span>
                    {{ (liveCorrectAfterT * 100).toFixed(1) }}%
                    <span class="f-delta">+{{ ((liveCorrectAfterT - parseFloat(liveParams.pKnown)) * 100).toFixed(1) }}%</span>
                  </div>
                </div>
                <div class="f-card f-wrong">
                  <div class="f-title">答错时 P(k|wrong)</div>
                  <div class="f-eq">
                    <span class="f-frac">
                      <span class="f-num">K·S</span>
                      <span class="f-den">K·S + (1−K)·(1−G)</span>
                    </span>
                  </div>
                  <div class="f-res err">
                    → {{ (liveWrongResult * 100).toFixed(1) }}%
                    <span class="f-arrow">→</span>
                    {{ (liveWrongAfterT * 100).toFixed(1) }}%
                    <span class="f-delta neg">{{ ((liveWrongResult - parseFloat(liveParams.pKnown)) * 100).toFixed(1) }}%</span>
                  </div>
                </div>
              </div>
              <div class="f-note">
                K=P(known)={{ liveParams.pKnown }}, S={{ liveParams.pSlip }}, G={{ liveParams.pGuess }}, T={{ liveParams.pLearn }}
              </div>
            </div>
          </div>

          <!-- Demo Panel (inline when active) -->
          <div v-if="showDemo" class="bkt-card card-demo">
            <div class="bc-hd">实时答题演示</div>
            <div class="demo-body">
              <div class="demo-col">
                <div class="demo-label">答题前</div>
                <div class="demo-val">{{ (demoBefore * 100).toFixed(0) }}%</div>
                <div class="demo-bar"><div class="demo-fill" :style="{ width: demoBefore*100+'%' }" /></div>
              </div>
              <div class="demo-mid">
                <button class="btn-ok" @click="simulateAnswer(true)" :disabled="demoSubmitting">✓ 对</button>
                <button class="btn-ng" @click="simulateAnswer(false)" :disabled="demoSubmitting">✗ 错</button>
                <span class="demo-reset" @click="resetDemo">重置</span>
              </div>
              <div class="demo-col">
                <div class="demo-label">答题后</div>
                <div class="demo-val after">
                  {{ (demoAfter * 100).toFixed(0) }}%
                  <span class="demo-chg" :class="demoDelta >= 0 ? 'up' : 'dn'">
                    {{ demoDelta >= 0 ? '+' : '' }}{{ (demoDelta * 100).toFixed(1) }}%
                  </span>
                </div>
                <div class="demo-bar"><div class="demo-fill after" :style="{ width: demoAfter*100+'%' }" /></div>
              </div>
            </div>
            <div v-if="demoStepDetail" class="demo-detail">
              <table class="dt-table">
                <tr><td>贝叶斯后验</td><td>{{ demoStepDetail.bayes_numerator }} / {{ demoStepDetail.bayes_denominator }}</td><td>= <strong>{{ (demoStepDetail.p_after_bayes * 100).toFixed(1) }}%</strong></td></tr>
                <tr><td>+ 学习转移</td><td>(1-P) × T</td><td>= +{{ (demoStepDetail.learn_delta * 100).toFixed(1) }}%</td></tr>
                <tr><td colspan="3" class="dt-final">最终 = <strong>{{ (demoStepDetail.p_final * 100).toFixed(1) }}%</strong></td></tr>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, WarningFilled } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import api from '@/api/index'

// ═══ Types ═══
interface MasteryItem { name: string; pKnown: number; attempts: number; correctRate: number; paramSource?: string; params?: Record<string, any>; historySummary?: HistoryStep[] }
interface HistoryStep { step: number; correct: boolean; p_before: number; p_after: number }
interface BKTMetrics { total_predictions: number; rmse: number; avg_log_likelihood: number; concepts_with_data: number; concepts_fitted: number }
interface ModelInfo { version: string; default_params: Record<string, number>; note_v4_fix?: string }
interface EMResult { concept: string; status: string; params?: any; rmse?: number }

// ═══ State ═══
const selectedConcept = ref<MasteryItem | null>(null)
const showDemo = ref(false)
const loading = ref(true)
const error = ref('')
const emFitting = ref(false)
const demoBefore = ref(0.3)
const demoAfter = ref(0.3)
const demoDelta = ref(0)
const demoSubmitting = ref(false)
const demoStepDetail = ref<any>(null)
const currentLearnParam = ref(0.2)

const masteryList = ref<MasteryItem[]>([])
const metrics = ref<BKTMetrics>({ total_predictions: 0, rmse: 0, avg_log_likelihood: 0, concepts_with_data: 0, concepts_fitted: 0 })
const modelInfo = ref<ModelInfo>({ version: '', default_params: {} })
const emFitResults = ref<EMResult[]>([])
const lineRef = ref<HTMLElement | null>(null)
let chartInstance: echarts.ECharts | null = null

// ═══ Computed ═══
const hasRealHistory = computed(() => {
  const item = selectedConcept.value || masteryList.value[0]
  return !!(item && item.historySummary && item.historySummary.length > 2)
})

const totalConcepts = computed(() => masteryList.value.length)
const avgMastery = computed(() => {
  if (!masteryList.value.length) return 0
  return masteryList.value.reduce((s, m) => s + m.pKnown, 0) / masteryList.value.length
})
const totalAttempts = computed(() => masteryList.value.reduce((s, m) => s + (m.attempts || 0), 0))
const masteredCount = computed(() => masteryList.value.filter(m => m.pKnown >= 0.85).length)
const weakCount = computed(() => masteryList.value.filter(m => m.pKnown < 0.35).length)

const liveParams = computed(() => {
  const item = selectedConcept.value || masteryList.value[0]
  const p = item?.params
  const dp = modelInfo.value.default_params
  return {
    pInitial: (p?.p_initial ?? dp['p_initial'] ?? 0.3).toFixed(2),
    pKnown: (p?.p_initial ?? dp['p_initial'] ?? 0.3).toFixed(2),
    pLearn: (p?.p_learn ?? dp['p_learn'] ?? 0.2).toFixed(2),
    pGuess: (p?.p_guess ?? dp['p_guess'] ?? 0.15).toFixed(2),
    pSlip: (p?.p_slip ?? dp['p_slip'] ?? 0.1).toFixed(2),
  }
})

// Bayesian calculation: correct
const liveCorrectResult = computed(() => {
  const pk = parseFloat(liveParams.value.pKnown), ps = parseFloat(liveParams.value.pSlip)
  const pg = parseFloat(liveParams.value.pGuess)
  const num = pk * (1 - ps), den = num + (1 - pk) * pg
  return den > 1e-10 ? num / den : pk
})
const liveCorrectAfterT = computed(() => {
  const pt = parseFloat(liveParams.value.pLearn)
  return Math.min(0.99, liveCorrectResult.value + (1 - liveCorrectResult.value) * pt)
})

// Bayesian calculation: wrong
const liveWrongResult = computed(() => {
  const pk = parseFloat(liveParams.value.pKnown), ps = parseFloat(liveParams.value.pSlip)
  const pg = parseFloat(liveParams.value.pGuess)
  const num = pk * ps, den = num + (1 - pk) * (1 - pg)
  return den > 1e-10 ? num / den : pk
})
const liveWrongAfterT = computed(() => {
  const pt = parseFloat(liveParams.value.pLearn)
  return Math.min(0.99, liveWrongResult.value + (1 - liveWrongResult.value) * pt)
})

// ═══ Helpers (完全照搬RAG页面颜色) ═══
// RAG颜色方案：dense蓝 → bm25绿 → rrf橙 → rerank紫（循环）
const RAG_COLORS = ['#2563EB', '#10B981', '#F59E0B', '#8B5CF6']
function ragColor(idx: number): string {
  return RAG_COLORS[idx % RAG_COLORS.length]
}
function probColor(p: number): string {
  if (p >= 0.85) return '#1D4ED8'
  if (p >= 0.6) return '#2563EB'
  if (p >= 0.35) return '#60A5FA'
  return '#93C5FD'
}
function lvlLabel(p: string | number): string {
  const n = typeof p === 'number' ? p : parseFloat(p as string)
  if (n >= 0.85) return '精通'; if (n >= 0.6) return '熟悉'; if (n >= 0.35) return '学习中'; return '入门'
}
function lvlClass(p: number): string {
  if (p >= 0.85) return 'ok'; if (p >= 0.6) return 'info'; if (p >= 0.35) return 'warn'; return 'new'
}
function rmseCls(r?: number): string {
  if (!r) return ''
  if (r < 0.25) return 'ok'; if (r < 0.35) return 'warn'; return 'err'
}

function selectConcept(item: MasteryItem) {
  selectedConcept.value = item
  renderLearningCurve()
  if (item.params?.p_learn !== undefined) currentLearnParam.value = item.params.p_learn
}

// ═══ Actions ═══
async function triggerEmFit() {
  emFitting.value = true
  try {
    const res = await api.post('/bkt/em-fit')
    emFitResults.value = res.data.results || []
    ElMessage.success(`EM拟合完成: ${res.data.fitted} 个成功`)
    loadBktData()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'EM拟合失败')
  } finally { emFitting.value = false }
}

function toggleDemo() { showDemo.value = !showDemo.value }

function resetDemo() {
  const item = selectedConcept.value || masteryList.value[0]
  demoBefore.value = item ? item.pKnown : 0.3
  demoAfter.value = demoBefore.value
  demoDelta.value = 0
  demoStepDetail.value = null
}

async function simulateAnswer(correct: boolean) {
  if (demoSubmitting.value) return
  demoSubmitting.value = true
  try {
    const conceptName = selectedConcept.value?.name || masteryList.value[0]?.name || 'Python基础'
    const res = await api.post('/bkt/answer', { concept: conceptName, is_correct: correct })
    const d = res.data
    demoAfter.value = d.p_known || demoBefore.value
    demoDelta.value = demoAfter.value - demoBefore.value
    demoStepDetail.value = d.update_step || null
    loadBktData()
  } catch {
    // Fallback: local bayesian calc
    const pk = demoBefore.value
    const ps = parseFloat(liveParams.value.pSlip), pg = parseFloat(liveParams.value.pGuess), pt = parseFloat(liveParams.value.pLearn)
    let post: number
    if (correct) { const n = pk * (1 - ps), dn = n + (1 - pk) * pg; post = dn > 1e-10 ? n / dn : pk }
    else { const n = pk * ps, dn = n + (1 - pk) * (1 - pg); post = dn > 1e-10 ? n / dn : pk }
    const final = Math.min(0.99, post + (1 - post) * pt)
    demoAfter.value = final
    demoDelta.value = final - pk
    demoBefore.value = final
  } finally { demoSubmitting.value = false }
}

// ═══ Chart ═══
function renderLearningCurve() {
  if (!lineRef.value) return
  chartInstance = chartInstance || echarts.init(lineRef.value)
  const targetItem = selectedConcept.value || masteryList.value[0]
  const history = targetItem?.historySummary

  if (history && history.length > 2) {
    // Real history data
    const xData = history.map(h => `#${h.step}`)
    const yData = history.map(h => Math.round(h.p_before * 100))
    chartInstance.setOption({
      tooltip: { trigger: 'axis', formatter: (p: any) => `${p[0].name}<br/>P(known): <b>${p[0].value}%</b>` },
      grid: { top: 20, right: 24, bottom: 28, left: 48 },
      xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11 }, boundaryGap: false },
      yAxis: { type: 'value', name: '%', min: 0, max: 100, axisLabel: { fontSize: 11, formatter: '{value}%' }, splitLine: { lineStyle: { color: '#F1F5F9' } } },
      series: [{
        type: 'line', data: yData, smooth: true,
        lineStyle: { color: '#2563EB', width: 2.5 },
        areaStyle: { color: '#EBF4FF' },
        itemStyle: { color: (d: any) => history[d.dataIndex]?.correct ? '#1D4ED8' : '#93C5FD' },
        symbol: 'circle', symbolSize: 7,
      }],
    })
  } else {
    // BKT forward simulation (24 steps)
    const SIM_STEPS = 24
    const item = targetItem || masteryList.value[0] || {}
    const params = item.params || {}
    const dp = modelInfo.value.default_params
    const pT = parseFloat(params?.p_learn || dp['p_learn']) || 0.20
    const pG = parseFloat(params?.p_guess || dp['p_guess']) || 0.15
    const pS = parseFloat(params?.p_slip || dp['p_slip']) || 0.10
    let p = parseFloat(params?.p_initial || dp['p_initial']) || 0.30
    const predData: number[] = [Math.round(p * 100)]
    const predLabels: string[] = ['初始']
    const simCorrect: boolean[] = []
    for (let i = 1; i <= SIM_STEPS; i++) {
      const diff = 0.55 + 0.2 * Math.sin((i / SIM_STEPS) * Math.PI * 1.5)
      const isCorrect = Math.random() < diff
      simCorrect.push(isCorrect)
      if (isCorrect) { const n = p * (1 - pS), d = n + (1 - p) * pG; p = d > 1e-10 ? n / d : p }
      else { const n = p * pS, d = n + (1 - p) * (1 - pG); p = d > 1e-10 ? n / d : p }
      p = Math.min(0.99, p + (1 - p) * pT)
      predData.push(Math.round(p * 100))
      predLabels.push(`#${i}`)
    }
    chartInstance.setOption({
      tooltip: { trigger: 'axis', formatter: (p: any) => `${p[0].name}<br/>P(known): <b>${p[0].value}%</b>` },
      legend: { data: ['模拟轨迹', '答对', '答错'], bottom: 2, textStyle: { fontSize: 11 } },
      grid: { top: 20, right: 24, bottom: 42, left: 48 },
      xAxis: { type: 'category', data: predLabels, axisLabel: { fontSize: 11 }, boundaryGap: false },
      yAxis: { type: 'value', name: '%', min: 0, max: 100, axisLabel: { fontSize: 11, formatter: '{value}%' }, splitLine: { lineStyle: { color: '#F1F5F9' } } },
      series: [
        { name: '模拟轨迹', type: 'line', data: predData, smooth: true, lineStyle: { color: '#2563EB', width: 2.5 }, symbol: 'none',
          areaStyle: { color: '#EBF4FF' } },
        { name: '答对', type: 'scatter', data: predData.map((v, i) => simCorrect[i] ? [i, v] : null), symbolSize: 8, itemStyle: { color: '#1D4ED8' } },
        { name: '答错', type: 'scatter', data: predData.map((v, i) => !simCorrect[i] ? [i, v] : null), symbolSize: 8, itemStyle: { color: '#93C5FD' } },
      ],
    })
  }
}

// ═══ Data Load ═══
async function loadBktData() {
  error.value = ''
  try {
    const bktRes = await api.get('/bkt/status')
    const bktData = bktRes.data

    if (bktData?.concepts?.length > 0) {
      masteryList.value = bktData.concepts.map((c: any) => ({
        name: c.name, pKnown: Math.min(0.99, Math.max(0.01, c.p_known || 0)),
        attempts: c.attempts || 0, correctRate: c.correct_rate || 0,
        paramSource: c.params?.source || 'default', params: c.params || null,
        historySummary: c.history_summary || [],
      })).sort((a: MasteryItem, b: MasteryItem) => b.pKnown - a.pKnown)
      metrics.value = bktData.metrics || metrics.value
      modelInfo.value = bktData.model_info || modelInfo.value
    } else {
      try {
        const r = await api.get('/profile/me')
        const kb: Record<string, number> = r.data?.knowledge_base || {}
        const entries = Object.entries(kb)
        if (entries.length > 0) {
          const maxV = Math.max(...entries.map(([, v]) => Number(v) || 0))
          const isPct = maxV > 1
          masteryList.value = entries.map(([name, val]) => ({
            name, pKnown: isPct ? Math.min(0.99, Math.max(0.01, Number(val) / 100)) : Math.min(0.99, Math.max(0.01, Number(val))),
            attempts: 0, correctRate: 0, paramSource: 'default',
          })).sort((a, b) => b.pKnown - a.pKnown)
        }
      } catch { /* ignore */ }
      if (masteryList.value.length === 0) {
        error.value = '暂无知识点数据，请先完成学习路径或答题'
      }
    }

    if (masteryList.value.length > 0 && !selectedConcept.value) selectedConcept.value = masteryList.value[0]
    renderLearningCurve()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    error.value = err?.response?.data?.detail || err?.message || '加载失败'
  } finally { loading.value = false }
}

watch(selectedConcept, () => { renderLearningCurve(); if (selectedConcept.value?.params?.p_learn) currentLearnParam.value = selectedConcept.value.params.p_learn })

onUnmounted(() => { if (chartInstance) { chartInstance.dispose(); chartInstance = null } })
onMounted(loadBktData)
</script>

<style scoped>
/* ═══ Layout (Pure Blue-White) ═══ */
.bkt { height: 100%; display: flex; flex-direction: column; overflow: hidden; background: var(--bg-page) }

.bkt-bar { display: flex; align-items: flex-start; justify-content: space-between; padding: 20px 24px 14px; flex-shrink: 0; background: var(--bg-card); border-bottom: 1px solid var(--border) }
.bkt-bar-l h1 { font-size: var(--font-xl); font-weight: 700; margin: 0; color: var(--text-primary) }
.bkt-bar-l p { font-size: var(--font-sm); color: var(--text-secondary); margin-top: 3px }
.bkt-bar-l strong { color: var(--primary) }
.bkt-bar-r { display: flex; gap: 10px; align-items: center }

.bkt-stats { display: flex; gap: 0; padding: 10px 24px; flex-shrink: 0; background: var(--bg-card); border-bottom: 1px solid var(--border) }
.bs-item { flex: 1; text-align: center; padding: 4px 0 }
.bs-v { font-size: 18px; font-weight: 700; display: block; color: var(--text-primary) }
.bs-l { font-size: 10px; color: var(--text-muted); margin-top: 2px }

.bkt-body { flex: 1; overflow: hidden; display: flex; flex-direction: column; padding: 16px 24px 20px }
.bkt-main { display: flex; gap: 16px; flex: 1; min-height: 0; overflow: hidden }

.bkt-left { width: 280px; flex-shrink: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 12px }

.bkt-right { flex: 1; min-width: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 12px }

.bkt-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); overflow: hidden }
.bc-hd { padding: 12px 16px; font-size: var(--font-sm); font-weight: 600; display: flex; align-items: center; gap: 8px; color: var(--text-secondary); border-bottom: 1px solid var(--bg-muted) }
.bc-bd { padding: 12px 16px }
.chart-sub { font-weight: 400; color: var(--text-muted); font-size: var(--font-xs) }
.mode-badge { font-size: 10px; padding: 2px 10px; border-radius: 999px; margin-left: auto; font-weight: 600; background: var(--primary-light); color: var(--primary) }

/* ═══ Concept List (Blue-White) ═══ */
.concept-row { padding: 10px 0; cursor: pointer; transition: all .15s; border-bottom: 1px solid var(--bg-page) }
.concept-row:last-child { border-bottom: none }
.concept-row:hover { background: var(--bg-page); margin: 0 -16px; padding: 10px 16px; border-radius: var(--radius-sm) }
.concept-row.active { background: var(--primary-light); margin: 0 -16px; padding: 10px 16px; border-radius: var(--radius-sm) }
.concept-row.prior { opacity: .85 }
.concept-row.prior:hover { opacity: 1 }

.cr-info { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px }
.cr-name { font-size: var(--font-sm); font-weight: 500; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-secondary) }
.cr-pct { font-size: var(--font-sm); font-weight: 700; flex-shrink: 0; margin-left: 8px; color: var(--primary) }

.cr-bar-wrap { height: 6px; background: var(--bg-muted); border-radius: var(--radius-sm); overflow: hidden }
.cr-bar { height: 100%; border-radius: var(--radius-sm); transition: width .6s ease }

.cr-meta { display: flex; align-items: center; gap: 6px; margin-top: 5px; font-size: var(--font-xs) }
.cr-tag { padding: 1px 8px; border-radius: var(--radius-sm); font-weight: 600; font-size: 10px; background: var(--primary-light); color: var(--primary) }
.cr-n { color: var(--text-muted) }
.cr-badge { font-size: 9px; padding: 0 5px; border-radius: var(--radius-sm); font-weight: 700; background: var(--primary-light); color: var(--primary-hover) }

.cr-more { text-align: center; font-size: var(--font-xs); color: var(--text-muted); padding: 8px 0 2px }

.params-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px }
.pp-cell { background: var(--bg-page); border-radius: var(--radius-md); padding: 12px 10px; text-align: center; border: 1px solid var(--bg-muted) }
.pp-k { display: block; font-size: 12px; font-weight: 700; color: var(--primary); font-family: monospace }
.pp-v { display: block; font-size: 18px; font-weight: 700; font-family: monospace; margin: 3px 0; color: var(--text-primary) }
.pp-d { display: block; font-size: 10px; color: var(--text-muted) }

.em-compact { border-top: 1px dashed var(--border); padding-top: 10px }
.em-title { font-size: var(--font-xs); font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; display: flex; align-items: center; gap: 6px }
.em-cnt { font-weight: 400; color: var(--text-muted); background: var(--bg-muted); padding: 1px 8px; border-radius: var(--radius-sm); font-size: 10px }
.em-row { display: flex; align-items: center; gap: 6px; padding: 5px 0; font-size: var(--font-xs) }
.em-row:last-child { border-bottom: none }
.em-n { flex: 1; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-secondary) }
.em-p { font-family: monospace; color: var(--text-secondary) }
.em-r { font-family: monospace; font-weight: 700; color: var(--primary) }

.metrics-inline { display: flex; gap: 16px; margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border); font-size: var(--font-xs); color: var(--text-secondary) }
.metrics-inline strong { font-weight: 600; color: var(--text-primary) }

/* ═══ Chart (HERO) ═══ */
.card-hero { flex-shrink: 0; overflow: hidden }
.chart-area { height: 280px }

.formula-body { font-size: var(--font-xs) }
.f-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px }
.f-card { background: var(--bg-page); border-radius: var(--radius-md); padding: 14px; border: 1px solid var(--border) }
.f-correct { border-color: var(--primary-light) }
.f-wrong { border-color: var(--red-light, #FEE2E2) }
.f-title { font-size: var(--font-xs); font-weight: 600; color: var(--text-secondary); margin-bottom: 8px }
.f-frac { display: flex; flex-direction: column; align-items: center }
.f-num { border-bottom: 1.5px solid var(--text-muted); padding: 4px 8px; font-family: 'Times New Roman', serif; font-style: italic; font-size: 13px; color: var(--text-secondary) }
.f-den { padding: 4px 8px; font-family: 'Times New Roman', serif; font-style: italic; font-size: 13px; color: var(--text-muted) }
.f-res { margin-top: 8px; font-size: 13px; font-weight: 600; text-align: center; padding: 6px; border-radius: var(--radius-sm) }
.f-res.ok { background: var(--primary-light); color: var(--primary) }
.f-res.err { background: var(--red-light, #FEF2F2); color: var(--red, #DC2626) }
.f-arrow { margin: 0 4px; color: var(--text-muted) }
.f-delta { font-size: 11px; margin-left: 4px; color: var(--primary) }
.f-delta.neg { color: var(--red, #DC2626) }
.f-note { margin-top: 10px; padding: 8px 10px; background: var(--bg-page); border-radius: var(--radius-sm); font-size: var(--font-xs); color: var(--text-secondary); font-family: monospace }

.demo-body { display: flex; align-items: stretch; gap: 16px }
.demo-col { flex: 1; text-align: center }
.demo-label { font-size: var(--font-xs); color: var(--text-muted); margin-bottom: 4px }
.demo-val { font-size: 28px; font-weight: 800; font-family: monospace; line-height: 1.2; color: var(--primary) }
.demo-val.after { color: var(--primary-hover) }
.demo-chg { font-size: 13px; font-weight: 600; margin-left: 3px; color: var(--primary) }
.demo-chg.dn { color: var(--red, #DC2626) }
.demo-bar { height: 6px; background: var(--bg-muted); border-radius: var(--radius-sm); margin-top: 6px; overflow: hidden }
.demo-fill { height: 100%; border-radius: var(--radius-sm); transition: all .35s ease; background: var(--primary) }
.demo-fill.after { background: var(--primary-hover); opacity: .85 }

.demo-mid { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; padding-top: 22px }
.btn-ok, .btn-ng { padding: 8px 20px; border: none; border-radius: var(--radius-sm); cursor: pointer; font-size: 13px; font-weight: 600; transition: all .12s }
.btn-ok:disabled, .btn-ng:disabled { opacity: .45; cursor: not-allowed }
.btn-ok { background: var(--primary-light); color: var(--primary-hover) }
.btn-ok:hover:not(:disabled) { background: #BFDBFE }
.btn-ng { background: var(--red-light, #FEE2E2); color: var(--red, #DC2626) }
.btn-ng:hover:not(:disabled) { background: #FECACA }
.demo-reset { font-size: var(--font-xs); color: var(--text-muted); cursor: pointer; text-decoration: underline }

.demo-detail { margin-top: 10px; border-top: 1px dashed var(--border); padding-top: 8px }
.dt-table { width: 100%; border-collapse: collapse; font-size: var(--font-xs); font-family: monospace }
.dt-table td { padding: 4px 6px; color: var(--text-secondary); border-bottom: 1px solid var(--bg-muted) }
.dt-table td:last-child { font-weight: 600; color: var(--text-primary) }
.dt-final { background: var(--bg-page); font-weight: 600 !important }

.bkt-loading { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--text-muted) }
.spin { animation: spin 1.2s linear infinite }
@keyframes spin { to { transform: rotate(360deg) } }
.bkt-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--text-muted) }

/* Responsive */
@media (max-width: 1100px) {
  .bkt-left { width: 240px }
  .f-row { grid-template-columns: 1fr }
}
@media (max-width: 900px) {
  .bkt-left { display: none }
  .chart-area { height: 260px }
}
</style>
