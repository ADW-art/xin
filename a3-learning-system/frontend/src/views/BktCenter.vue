<template>
  <div class="bkt-center">
    <!-- ═══════════ HEADER ═══════════ -->
    <div class="bkt-top">
      <div class="bkt-top-l">
        <h1>BKT 知识追踪中心</h1>
        <p>基于<strong>贝叶斯四参数模型 v4</strong>的知识追踪，用后验概率推算真正的掌握程度</p>
      </div>
      <div class="bkt-top-r">
        <el-button size="small" :type="showDemo ? 'warning' : 'default'" @click="toggleDemo">
          <el-icon :size="14"><VideoPlay /></el-icon> {{ showDemo ? '停止演示' : '答题演示' }}
        </el-button>
        <el-button size="small" type="primary" plain @click="triggerEmFit" :loading="emFitting" :disabled="totalConcepts === 0">
          <el-icon :size="14"><DataAnalysis /></el-icon> EM拟合参数
        </el-button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="bkt-loading">
      <el-icon class="spin" :size="36"><Loading /></el-icon>
      <p>加载 BKT 知识追踪数据...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="bkt-empty">
      <el-empty :description="error">
        <el-button type="primary" @click="loadBktData">重新加载</el-button>
      </el-empty>
    </div>

    <!-- Empty State -->
    <div v-else-if="masteryList.length === 0" class="bkt-empty">
      <el-empty description="暂无 BKT 知识追踪数据">
        <template #extra>
          <p class="bkt-empty-hint">开始对话学习后，知识掌握数据将在此展示</p>
          <el-button type="primary" @click="$router.push('/chat')">前往对话</el-button>
        </template>
      </el-empty>
    </div>

    <!-- Normal Content -->
    <div v-else class="bkt-main">
      <!-- Left: Mastery Bars + Weak Points -->
      <aside class="bkt-left">
        <!-- Knowledge Mastery -->
        <div class="bkt-panel">
          <div class="bkt-panel-hd">
            知识掌握概率 P(known)
            <span v-if="metrics.total_predictions > 0" class="metric-badge">
              RMSE: {{ metrics.rmse }}
            </span>
          </div>
          <div class="bkt-panel-bd">
            <div v-for="item in masteryList" :key="item.name" class="mastery-row" @click="selectedConcept = item">
              <div class="mr-header">
                <span class="mr-name">{{ item.name }}</span>
                <span class="mr-pct" :style="{ color: probColor(item.pKnown) }">{{ (item.pKnown * 100).toFixed(0) }}%</span>
              </div>
              <div class="mr-bar-wrap">
                <div class="mr-bar" :style="{ width: (item.pKnown * 100) + '%', background: probBarColor(item.pKnown) }">
                  <div v-if="item.pKnown > 0.6" class="mr-shine" />
                </div>
              </div>
              <div class="mr-footer">
                <span class="mr-level" :class="levelClass(item.pKnown)">{{ levelLabel(item.pKnown) }}</span>
                <span class="mr-attempts">{{ item.attempts || 0 }}次答题</span>
                <span v-if="item.paramSource" class="param-src-badge" :class="'src-' + item.paramSource">{{ paramSourceLabel(item.paramSource) }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Weak Points -->
        <div class="bkt-panel panel-weak">
          <div class="bkt-panel-hd">薄弱知识点</div>
          <div class="bkt-panel-bd">
            <div v-if="weakPoints.length === 0" class="empty-safe">未检测到薄弱点</div>
            <div v-for="w in weakPoints" :key="w.name" class="weak-row">
              <div class="weak-status" :class="w.risk" />
              <div class="weak-info">
                <span class="weak-name">{{ w.name }}</span>
                <span class="weak-reason">{{ w.reason }}</span>
              </div>
              <span class="weak-action" @click="$router.push('/chat')">加强 →</span>
            </div>
          </div>
        </div>
      </aside>

      <!-- Center: Curve + Formula + Demo -->
      <main class="bkt-center-col">
        <!-- ECharts Line Chart: Learning Curve (v4: real time-series) -->
        <div class="bkt-panel panel-chart">
          <div class="bkt-panel-hd">
            掌握概率变化曲线（时间序列）
            <span v-if="selectedConcept" class="chart-subtitle">— {{ selectedConcept.name }}</span>
          </div>
          <div class="bkt-panel-bd">
            <div ref="lineRef" style="height:280px" />
          </div>
        </div>

        <!-- BKT Formula Explanation (v4: dynamic params with source) -->
        <div class="bkt-panel panel-formula">
          <div class="bkt-panel-hd">BKT 贝叶斯更新公式（Corbett & Anderson 1995）</div>
          <div class="bkt-panel-bd formula-content">
            <div class="formula-grid">
              <div class="formula-card">
                <div class="formula-title">答对时 P(known|correct)</div>
                <div class="formula-eq">
                  <span class="frac">
                    <span class="frac-top">P(known) × (1 − P(S))</span>
                    <span class="frac-bot">P(known)×(1−P(S)) + (1−P(known))×P(G)</span>
                  </span>
                </div>
              </div>
              <div class="formula-card">
                <div class="formula-title">答错时 P(known|wrong)</div>
                <div class="formula-eq">
                  <span class="frac">
                    <span class="frac-top">P(known) × P(S)</span>
                    <span class="frac-bot">P(known)×P(S) + (1−P(known))×(1−P(G))</span>
                  </span>
                </div>
              </div>
            </div>
            <!-- v4: 动态参数展示（从API获取真实值） -->
            <div class="params-grid">
              <div class="param-item" v-for="(val, key) in displayParams" :key="key">
                <strong>{{ paramLabel(key) }}={{ val.value }}</strong>
                <span :class="'src-tag src-' + val.source">{{ paramSourceLabel(val.source) }}</span>
              </div>
            </div>
            <div class="formula-note" v-if="modelInfo.note_v4_fix">
              <el-icon><InfoFilled /></el-icon> {{ modelInfo.note_v4_fix }}
            </div>
          </div>
        </div>

        <!-- Prediction Metrics (v4 new) -->
        <div v-if="metrics.total_predictions > 0" class="bkt-panel panel-metrics">
          <div class="bkt-panel-hd">模型预测精度</div>
          <div class="bkt-panel-bd">
            <div class="metrics-grid">
              <div class="metric-item">
                <span class="metric-label">RMSE</span>
                <span class="metric-value" :class="rmseLevel(metrics.rmse)">{{ metrics.rmse }}</span>
                <span class="metric-desc">越低越好 (&lt;0.35 优秀)</span>
              </div>
              <div class="metric-item">
                <span class="metric-label">平均对数似然</span>
                <span class="metric-value">{{ metrics.avg_log_likelihood }}</span>
                <span class="metric-desc">越高越好</span>
              </div>
              <div class="metric-item">
                <span class="metric-label">总预测次数</span>
                <span class="metric-value">{{ metrics.total_predictions }}</span>
                <span class="metric-desc">答题记录总数</span>
              </div>
              <div class="metric-item">
                <span class="metric-label">已拟合知识点</span>
                <span class="metric-value">{{ metrics.concepts_fitted }}/{{ metrics.concepts_with_data }}</span>
                <span class="metric-desc">EM参数估计覆盖</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Before/After Demo (v4: uses actual node params) -->
        <div v-if="showDemo" class="bkt-panel panel-demo">
          <div class="bkt-panel-hd">答题前后变化演示（使用实际参数）</div>
          <div class="bkt-panel-bd">
            <div class="demo-flow">
              <div class="demo-before">
                <div class="demo-label">答题前</div>
                <div class="demo-concept">{{ demoConcept?.name || '选择知识点' }}</div>
                <div class="demo-pct" :style="{ color: probColor(demoBefore) }">{{ (demoBefore * 100).toFixed(0) }}%</div>
                <div class="demo-bar"><div class="demo-bar-fill" :style="{ width: (demoBefore*100)+'%', background: probBarColor(demoBefore) }" /></div>
              </div>
              <div class="demo-arrow">
                <div class="demo-answer-btns">
                  <button class="answer-btn correct" @click="simulateAnswer(true)">✓ 答对</button>
                  <button class="answer-btn wrong" @click="simulateAnswer(false)">✗ 答错</button>
                </div>
              </div>
              <div class="demo-after">
                <div class="demo-label">答题后</div>
                <div class="demo-concept">{{ demoConcept?.name || '—' }}</div>
                <div class="demo-pct after" :style="{ color: probColor(demoAfter) }">
                  {{ (demoAfter * 100).toFixed(0) }}%
                  <span class="demo-delta" :class="demoDelta >= 0 ? 'up' : 'down'">
                    {{ demoDelta >= 0 ? '+' : '' }}{{ (demoDelta * 100).toFixed(1) }}%
                  </span>
                </div>
                <div class="demo-bar"><div class="demo-bar-fill after-fill" :style="{ width: (demoAfter*100)+'%', background: probBarColor(demoAfter) }" /></div>
              </div>
            </div>
            <!-- v4: 分步计算明细 -->
            <div class="demo-explanation" v-if="demoExplanation">{{ demoExplanation }}</div>
            <div class="demo-steps" v-if="demoStepDetail">
              <div class="step-detail-header">计算过程分解</div>
              <table class="step-table">
                <tr>
                  <td>阶段1：贝叶斯后验</td>
                  <td>P({{ demoStepDetail.is_correct ? 'known|correct' : 'known|wrong' }})</td>
                  <td>= {{ demoStepDetail.bayes_numerator }} / {{ demoStepDetail.bayes_denominator }}</td>
                  <td>= <strong>{{ (demoStepDetail.p_after_bayes * 100).toFixed(1) }}%</strong></td>
                </tr>
                <tr>
                  <td>阶段2：学习转移 P(T)</td>
                  <td>+ (1-P) × {{ currentLearnParam }}</td>
                  <td>= +{{ (demoStepDetail.learn_delta * 100).toFixed(1) }}%</td>
                  <td>= <strong>{{ (demoStepDetail.p_after_learn * 100).toFixed(1) }}%</strong></td>
                </tr>
                <tr v-if="Math.abs(demoStepDetail.forget_delta) > 0.0001">
                  <td>阶段3：遗忘衰减 P(F)</td>
                  <td>× (1-P(F))</td>
                  <td>-{{ (demoStepDetail.forget_delta * 100).toFixed(1) }}%</td>
                  <td>= <strong>{{ (demoStepDetail.p_final * 100).toFixed(1) }}%</strong></td>
                </tr>
              </table>
            </div>
          </div>
        </div>
      </main>

      <!-- Right: Heatmap + Recommendations + EM Results -->
      <aside class="bkt-right">
        <!-- Heatmap -->
        <div class="bkt-panel">
          <div class="bkt-panel-hd">知识热力图</div>
          <div class="bkt-panel-bd heatmap-bd">
            <div class="heatmap-grid">
              <div
                v-for="cell in heatmapCells"
                :key="cell.name"
                class="heatmap-cell"
                :style="{ background: heatColor(cell.value) }"
                :title="cell.name + ': ' + (cell.value*100).toFixed(0) + '%'"
              >
                <span class="heatmap-label">{{ cell.name.slice(0,3) }}</span>
              </div>
            </div>
            <div class="heatmap-legend">
              <span>0%</span>
              <div class="heatmap-gradient" />
              <span>100%</span>
            </div>
          </div>
        </div>

        <!-- Recommendations -->
        <div class="bkt-panel">
          <div class="bkt-panel-hd">推荐学习原因</div>
          <div class="bkt-panel-bd">
            <div v-if="recommendations.length === 0" class="empty-safe">无推荐</div>
            <div v-for="rec in recommendations" :key="rec.name" class="rec-row">
              <div class="rec-dot" :style="{ background: probColor(rec.pKnown) }" />
              <div class="rec-info">
                <span class="rec-name">{{ rec.name }}</span>
                <span class="rec-reason">{{ rec.reason }}</span>
              </div>
              <span class="rec-pct">{{ (rec.pKnown * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>

        <!-- EM Fit Results (v4 new) -->
        <div v-if="emFitResults.length > 0" class="bkt-panel panel-em">
          <div class="bkt-panel-hd">EM 拟合结果</div>
          <div class="bkt-panel-bd">
            <div v-for="r in emFitResults.slice(0, 5)" :key="r.concept" class="em-row">
              <div class="em-name">{{ r.concept }}</div>
              <div class="em-params">
                T={{ r.params?.p_learn?.toFixed(2) ?? '-' }}
                G={{ r.params?.p_guess?.toFixed(2) ?? '-' }}
                S={{ r.params?.p_slip?.toFixed(2) ?? '-' }}
              </div>
              <div class="em-rmse" :class="rmseLevel(r.rmse)">RMSE:{{ r.rmse?.toFixed(3) }}</div>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPlay, Loading, DataAnalysis, InfoFilled } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import api from '@/api/index'

// ═══════════ Types ═══════════
interface MasteryItem {
  name: string; pKnown: number; attempts: number; correctRate: number
  paramSource?: string; params?: Record<string, any>; historySummary?: HistoryStep[]
}
interface HistoryStep { step: number; correct: boolean; p_before: number; p_after: number }
interface WeakPoint { name: string; pKnown: number; reason: string; risk: string }
interface BKTMetrics {
  total_predictions: number; rmse: number; avg_log_likelihood: number
  concepts_with_data: number; concepts_fitted: number
}
interface ModelInfo { version: string; default_params: Record<string, number>; note_v4_fix?: string }
interface EMResult { concept: string; status: string; params?: any; rmse?: number }

// ═══════════ State ═══════════
const selectedConcept = ref<MasteryItem | null>(null)
const showDemo = ref(false)
const loading = ref(true)
const error = ref('')
const emFitting = ref(false)

// Demo state
const demoBefore = ref(0.3)
const demoAfter = ref(0.3)
const demoDelta = ref(0)
const demoConcept = ref<MasteryItem | null>(null)
const demoExplanation = ref('')
const demoStepDetail = ref<any>(null)
const currentLearnParam = ref(0.2)

// Data
const masteryList = ref<MasteryItem[]>([])
const metrics = ref<BKTMetrics>({ total_predictions: 0, rmse: 0, avg_log_likelihood: 0, concepts_with_data: 0, concepts_fitted: 0 })
const modelInfo = ref<ModelInfo>({ version: '', default_params: {} })
const emFitResults = ref<EMResult[]>([])

const lineRef = ref<HTMLElement | null>(null)

// Computed
const weakPoints = computed<WeakPoint[]>(() =>
  masteryList.value
    .filter(m => m.pKnown < 0.35)
    .map(m => ({
      name: m.name, pKnown: m.pKnown,
      reason: m.pKnown < 0.15 ? '严重薄弱，建议立即学习' : '掌握不足，建议加强练习',
      risk: m.pKnown < 0.15 ? 'high' : 'medium',
    }))
)

const heatmapCells = computed(() => masteryList.value.map(m => ({ ...m, value: m.pKnown })))

const recommendations = computed(() =>
  masteryList.value
    .filter(m => m.pKnown < 0.6 && m.pKnown >= 0.35)
    .sort((a, b) => a.pKnown - b.pKnown)
    .slice(0, 5)
    .map(m => ({
      ...m,
      reason: m.pKnown < 0.45 ? '即将达到薄弱阈值' : '有提升空间，建议巩固',
    }))
)

const totalConcepts = computed(() => masteryList.value.length)

// v4: 动态参数展示（优先使用选中概念的参数，否则用全局默认）
const displayParams = computed(() => {
  const item = selectedConcept.value || masteryList.value[0]
  if (item?.params) {
    return {
      p_initial: { value: item.params.p_initial?.toFixed(2) ?? '—', source: item.params.source ?? 'default' },
      p_learn:   { value: item.params.p_learn?.toFixed(2) ?? '—', source: item.params.source ?? 'default' },
      p_guess:   { value: item.params.p_guess?.toFixed(2) ?? '—', source: item.params.source ?? 'default' },
      p_slip:    { value: item.params.p_slip?.toFixed(2) ?? '—', source: item.params.source ?? 'default' },
    }
  }
  return {
    p_initial: { value: modelInfo.value.default_params['p_initial']?.toFixed(2) ?? '0.30', source: 'default' as string },
    p_learn:   { value: modelInfo.value.default_params['p_learn']?.toFixed(2) ?? '0.20', source: 'default' as string },
    p_guess:   { value: modelInfo.value.default_params['p_guess']?.toFixed(2) ?? '0.15', source: 'default' as string },
    p_slip:    { value: modelInfo.value.default_params['p_slip']?.toFixed(2) ?? '0.10', source: 'default' as string },
  }
})

// ═══════════ Helpers ═══════════
function probColor(p: number) {
  if (p >= 0.85) return '#1D4ED8'; if (p >= 0.6) return '#2563EB'
  if (p >= 0.35) return '#60A5FA'; return '#94A3B8'
}
function probBarColor(p: number) { return probColor(p) }

function levelLabel(p: number) { if (p >= 0.85) return '精通'; if (p >= 0.6) return '熟悉'; if (p >= 0.35) return '学习中'; return '入门' }
function levelClass(p: number) { if (p >= 0.85) return 'lvl-mastered'; if (p >= 0.6) return 'lvl-learning'; if (p >= 0.35) return 'lvl-begin'; return 'lvl-new' }

function heatColor(v: number) {
  if (v >= 0.85) return '#1D4ED8'; if (v >= 0.6) return '#2563EB'
  if (v >= 0.35) return '#60A5FA'; if (v > 0) return '#93C5FD'; return '#F1F5F9'
}

function paramSourceLabel(src: string): string {
  return { default: '经验默认', em_fitted: 'EM拟合', custom: '自定义' }[src] || src
}

function paramLabel(k: string): string {
  return { p_initial: 'P(L₀)', p_learn: 'P(T)', p_guess: 'P(G)', p_slip: 'P(S)' }[k] || k
}

function rmseLevel(rmse?: number): string {
  if (rmse === undefined || rmse === null) return 'rmse-fair'
  if (rmse <= 0.30) return 'rmse-excellent'
  if (rmse <= 0.40) return 'rmse-good'
  return 'rmse-fair'
}

// ═══════════ BKT Simulation (v4: uses actual node params) ═══════════

async function simulateAnswer(correct: boolean) {
  if (!demoConcept.value) {
    demoConcept.value = masteryList.value[0]
    if (!demoConcept.value) return
  }

  // v4: 调用真实后端 /api/bkt/answer → 获取 update_step 分步明细
  let step: any = null
  try {
    const r = await api.post('/bkt/answer', {
      concept: demoConcept.value.name,
      is_correct: correct,
      user_answer: correct ? '(答题演示-正确)' : '(答题演示-错误)',
    })
    step = r.data?.update_step
    if (step) {
      demoAfter.value = Math.min(0.99, Math.max(0.01, step.p_final))
      demoStepDetail.value = step
      demoExplanation.value =
        `${correct ? '答对' : '答错'}！` +
        `贝叶斯后验: ${(step.p_after_bayes * 100).toFixed(1)}% → ` +
        `学习转移: +${(step.learn_delta * 100).toFixed(1)}%` +
        (step.forget_delta ? ` → 遗忘衰减: -${(step.forget_delta * 100).toFixed(1)}%` : '') +
        ` = 最终 ${(demoAfter.value * 100).toFixed(0)}%` +
        ` [真实API - BKT v4]`
    }
    // 刷新 mastery list
    await loadBktData()
  } catch {
    // API 不可用时降级为本地计算
    const params = demoConcept.value.params || {}
    const pG = parseFloat(params.p_guess) || 0.15
    const pS = parseFloat(params.p_slip) || 0.1
    const pT = parseFloat(params.p_learn) || 0.2
    currentLearnParam.value = pT
    const p = demoBefore.value
    let num: number, den: number
    if (correct) { num = p * (1 - pS); den = num + (1 - p) * pG }
    else { num = p * pS; den = num + (1 - p) * (1 - pG) }
    const pBayes = num / den
    const learnDelta = (1 - pBayes) * pT
    demoAfter.value = Math.min(0.99, Math.max(0.01, pBayes + learnDelta))
    demoStepDetail.value = {
      is_correct: correct, bayes_numerator: num, bayes_denominator: den,
      p_after_bayes: pBayes, p_after_learn: demoAfter.value,
      p_final: demoAfter.value, learn_delta: learnDelta, forget_delta: 0,
    }
    demoExplanation.value =
      `${correct ? '答对' : '答错'}！本地计算(API离线): ${(demoAfter.value * 100).toFixed(0)}% [降级模式]`
  }

  demoDelta.value = demoAfter.value - demoBefore.value
  demoBefore.value = demoAfter.value

  demoBefore.value = demoAfter.value

  // Update the mastery item locally for visual feedback
  if (demoConcept.value) {
    const item = masteryList.value.find(m => m.name === demoConcept.value!.name)
    if (item) { item.pKnown = demoAfter.value; item.attempts++ }
  }
}

function toggleDemo() {
  showDemo.value = !showDemo.value
  if (showDemo.value) {
    demoBefore.value = 0.3
    demoAfter.value = 0.3
    demoDelta.value = 0
    demoConcept.value = masteryList.value[0] || null
    demoExplanation.value = ''
    demoStepDetail.value = null
  }
}

async function triggerEmFit() {
  emFitting.value = true
  try {
    const res = await api.post('/bkt/em-fit', {})
    emFitResults.value = res.data.results || []
    ElMessage.success(`EM拟合完成: ${res.data.fitted}个成功, ${res.data.skipped}个跳过`)
    // Reload to get updated params
    await loadBktData()
  } catch (e: any) {
    ElMessage.error('EM拟合失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    emFitting.value = false
  }
}

// ═══════════ ECharts Learning Curve (v4: real time-series line chart) ═══════════

function renderLearningCurve() {
  nextTick(() => {
    if (!lineRef.value) return
    const chart = echarts.init(lineRef.value)

    // v4: 使用 history_summary 绘制真正的学习曲线（时间序列）
    const targetItem = selectedConcept.value || masteryList.value[0]
    const history = targetItem?.historySummary || []

    if (history.length > 0) {
      const steps = history.map(h => h.step)
      const pValues = history.map(h => Math.round(h.p_after * 100))
      const correctMarks = history.map(h => h.correct ? '●' : '○')

      chart.setOption({
        tooltip: {
          trigger: 'axis',
          formatter: (p: any[]) => {
            const d = p[0]
            return `${targetItem.name}<br/>第${d.dataIndex + 1}题: ${history[d.dataIndex]?.correct ? '答对' : '答错'}<br/>P(known)=${d.value}%`
          },
        },
        grid: { top: 16, right: 24, bottom: 32, left: 48 },
        xAxis: {
          type: 'category',
          data: steps.map((_, i) => `#${i + 1}`),
          axisLabel: { fontSize: 10, color: '#94A3B8' },
          name: '答题序号',
          nameLocation: 'end',
          nameTextStyle: { fontSize: 10, color: '#94A3B8' },
        },
        yAxis: {
          type: 'value',
          min: 0,
          max: 100,
          axisLabel: { fontSize: 10, color: '#94A3B8', formatter: '{value}%' },
          splitLine: { lineStyle: { color: '#F1F5F9' } },
          name: 'P(known)',
          nameLocation: 'end',
          nameTextStyle: { fontSize: 10, color: '#94A3B8' },
        },
        series: [
          {
            type: 'line',
            data: pValues,
            smooth: true,
            symbol: (val: number, params: { dataIndex: number }) =>
              history[params.dataIndex]?.correct ? 'circle' : 'diamond',
            symbolSize: 8,
            lineStyle: { color: '#2563EB', width: 2.5 },
            itemStyle: {
              color: (p: { value: number }) => {
                const v = p.value
                if (v >= 85) return '#1D4ED8'
                if (v >= 60) return '#2563EB'
                if (v >= 35) return '#60A5FA'
                return '#94A3B8'
              },
            },
            areaStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: 'rgba(37,99,235,0.15)' },
                { offset: 1, color: 'rgba(37,99,235,0.01)' },
              ]),
            },
            markLine: {
              silent: true,
              symbol: 'none',
              lineStyle: { type: 'dashed', color: '#EF4444', width: 1.5 },
              data: [
                { yAxis: 85, label: { formatter: '精通线 85%', fontSize: 10, color: '#EF4444' } },
                { yAxis: 35, label: { formatter: '入门线 35%', fontSize: 10, color: '#94A3B8' } },
              ],
            },
            animationDuration: 1200,
          },
        ],
      })
    } else {
      // 无历史数据时的降级展示（柱状图）
      const items = masteryList.value.slice(0, 8)
      chart.setOption({
        tooltip: { trigger: 'axis', formatter: (p: { name: string; value: number }[]) => `${p[0].name}: ${p[0].value}%` },
        grid: { top: 12, right: 20, bottom: 24, left: 44 },
        xAxis: { type: 'category', data: items.map(m => m.name.slice(0, 4)), axisLabel: { fontSize: 10, color: '#94A3B8' } },
        yAxis: { type: 'value', min: 0, max: 100, axisLabel: { fontSize: 10, color: '#94A3B8', formatter: '{value}%' }, splitLine: { lineStyle: { color: '#F1F5F9' } } },
        series: [{
          type: 'bar', data: items.map(m => Math.round(m.pKnown * 100)),
          itemStyle: {
            color: (p: { value: number }) => {
              const v = p.value
              if (v >= 85) return '#1D4ED8'; if (v >= 60) return '#2563EB'
              if (v >= 35) return '#60A5FA'; return '#94A3B8'
            }, borderRadius: [4, 4, 0, 0]
          },
          barWidth: '60%',
          animationDuration: 1000,
        }],
      })
    }

    ;(lineRef.value as HTMLElement & { _chart?: echarts.ECharts })._chart = chart
  })
}

// ═══════════ Data Loading ═══════════
async function loadBktData() {
  loading.value = true
  error.value = ''
  try {
    const bktRes = await api.get('/bkt/status')
    const bktData = bktRes.data

    if (bktData?.concepts && bktData.concepts.length > 0) {
      // v4: 完整数据映射（含参数来源和历史）
      masteryList.value = bktData.concepts.map((c: any) => ({
        name: c.name,
        pKnown: Math.min(0.99, Math.max(0.01, c.p_known || 0)),
        attempts: c.attempts || 0,
        correctRate: c.correct_rate || 0,
        paramSource: c.params?.source || 'default',
        params: c.params || null,
        historySummary: c.history_summary || [],
      })).sort((a: MasteryItem, b: MasteryItem) => b.pKnown - a.pKnown)

      // v4: 预测指标
      metrics.value = bktData.metrics || metrics.value
      modelInfo.value = bktData.model_info || modelInfo.value
    } else {
      // Fallback: 从画像获取
      try {
        const r = await api.get('/profile/me')
        const kb: Record<string, number> = r.data?.knowledge_base || {}
        const entries = Object.entries(kb)
        if (entries.length > 0) {
          const maxVal = Math.max(...entries.map(([, v]) => Number(v) || 0))
          const isPercentScale = maxVal > 1
          masteryList.value = entries
            .map(([name, val]) => {
              const raw = Number(val) || 0
              const pKnown = isPercentScale
                ? Math.min(0.99, Math.max(0.01, raw / 100))
                : Math.min(0.99, Math.max(0.01, raw))
              return { name, pKnown, attempts: 0, correctRate: 0, paramSource: 'default' as string }
            })
            .sort((a, b) => b.pKnown - a.pKnown)
        }
      } catch { /* ignore */ }
    }

    // 加载答题次数补充
    try {
      const ar = await api.get('/assessment/records')
      const records = ar.data || []
      const attemptMap: Record<string, number> = {}
      records.forEach((rec: { concept?: string; question_id?: string }) => {
        const concept = rec.concept || rec.question_id
        if (concept) attemptMap[concept] = (attemptMap[concept] || 0) + 1
      })
      masteryList.value.forEach(m => { m.attempts = attemptMap[m.name] || m.attempts })
    } catch { /* ignore */ }

    renderLearningCurve()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    error.value = err?.response?.data?.detail || err?.message || 'BKT 数据加载失败'
    masteryList.value = []
    renderLearningCurve()
  } finally {
    loading.value = false
  }
}

// Watch selected concept changes to re-render chart
watch(selectedConcept, () => renderLearningCurve())

// Cleanup ECharts instance on unmount
onUnmounted(() => {
  if (lineRef.value) {
    const chart = (lineRef.value as HTMLElement & { _chart?: echarts.ECharts })._chart
    if (chart) {
      chart.dispose()
    }
  }
})

onMounted(loadBktData)
</script>

<style scoped>
/* ═══════════ Layout ═══════════ */
.bkt-center {
  height: calc(100dvh - var(--header-h));
  display: flex; flex-direction: column;
  background: var(--bg-page);
}
.bkt-top {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 16px 20px 12px; background: var(--bg-card); flex-shrink: 0;
  border-bottom: 1px solid var(--border);
}
.bkt-top-l h1 { font-size: var(--font-xl); font-weight: 700; }
.bkt-top-l p { font-size: var(--font-sm); color: var(--text-secondary); margin-top: 2px; }
.bkt-top-l strong { color: var(--primary); }
.bkt-top-r { flex-shrink: 0; display: flex; gap: 8px; }

.bkt-main { display: flex; flex: 1; overflow: hidden; }
.bkt-left { width: 300px; flex-shrink: 0; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; border-right: 1px solid var(--border); }
.bkt-center-col { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.bkt-right { width: 280px; flex-shrink: 0; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; border-left: 1px solid var(--border); }

/* ═══════════ Panel ═══════════ */
.bkt-panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; }
.bkt-panel-hd { padding: 10px 14px; font-size: var(--font-sm); font-weight: 600; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 8px; }
.bkt-panel-bd { padding: 12px 14px; }
.metric-badge { font-size: 11px; font-weight: 400; color: #94A3B8; background: #F1F5F9; padding: 1px 8px; border-radius: 10px; }
.chart-subtitle { font-weight: 400; color: var(--text-muted); font-size: var(--font-xs); }

/* ═══════════ Mastery Bars ═══════════ */
.mastery-row { padding: 10px 0; border-bottom: 1px solid var(--border); cursor: pointer; transition: background .15s; }
.mastery-row:last-child { border-bottom: none; }
.mastery-row:hover { background: rgba(37,99,235,.02); margin: 0 -14px; padding: 10px 14px; }
.mr-header { display: flex; justify-content: space-between; margin-bottom: 6px; align-items: center; }
.mr-name { font-size: var(--font-sm); font-weight: 500; }
.mr-pct { font-size: var(--font-sm); font-weight: 700; }
.mr-bar-wrap { height: 8px; background: #F1F5F9; border-radius: var(--radius-sm); overflow: hidden; }
.mr-bar { height: 100%; border-radius: var(--radius-sm); transition: width .8s ease; }
.mr-shine { position:absolute; right:0;top:0;bottom:0;width:20px;background:linear-gradient(90deg,transparent,#fff3);opacity:.4 }
.mr-footer { display: flex; justify-content: space-between; margin-top: 4px; font-size: 11px; align-items: center; gap: 4px; flex-wrap: wrap; }
.mr-level { padding: 1px 8px; border-radius: var(--radius-md); font-weight: 500; }
.lvl-mastered { background: rgba(29,78,216,.08); color: #1D4ED8; }
.lvl-learning { background: rgba(37,99,235,.08); color: #2563EB; }
.lvl-begin { background: rgba(96,165,250,.08); color: #60A5FA; }
.lvl-new { background: rgba(148,163,184,.08); color: #94A3B8; }
.mr-attempts { color: var(--text-muted); }

/* v4: 参数来源标签 */
.param-src-badge {
  font-size: 10px; padding: 0 6px; border-radius: 8px; font-weight: 500;
}
.src-default { background: #F1F5F9; color: #64748B; }
.src-em_fitted { background: #D1FAE5; color: #059669; }
.src-custom { background: #FEF3C7; color: #D97706; }
.src-tag { font-size: 10px; padding: 0 6px; border-radius: 8px; margin-left: 4px; font-weight: 500; }

/* ═══════════ Weak Points ═══════════ */
.panel-weak .bkt-panel-hd { color: var(--primary); }
.empty-safe { font-size: var(--font-xs); color: var(--primary); text-align: center; padding: 16px 0; }

/* ═══════════ Formula ═══════════ */
.formula-content { font-size: var(--font-xs); }
.formula-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.formula-card { background: #F8FAFC; border: 1px solid var(--border); border-radius: var(--radius-md); padding: 10px 12px; }
.formula-title { font-size: 11px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
.frac { display: flex; flex-direction: column; align-items: center; text-align: center; }
.frac-top { border-bottom: 1.5px solid #334155; padding: 2px 4px; font-family: 'Times New Roman', serif; font-style: italic; }
.frac-bot { padding: 2px 4px; font-family: 'Times New Roman', serif; font-style: italic; }
.params-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.param-item { display: flex; align-items: center; gap: 4px; font-size: 11px; }
.param-item strong { color: var(--text-primary); font-family: monospace; }
.formula-note { margin-top: 8px; padding: 6px 10px; background: #FEF3C7; border-radius: var(--radius-sm); font-size: 11px; color: #92400E; display: flex; align-items: center; gap: 4px; }

/* ═══════════ Metrics Panel ═══════════ */
.metrics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.metric-item { background: #F8FAFC; border-radius: var(--radius-md); padding: 10px; text-align: center; }
.metric-label { display: block; font-size: 11px; color: var(--text-secondary); margin-bottom: 2px; }
.metric-value { display: block; font-size: 18px; font-weight: 700; font-family: monospace; }
.metric-desc { display: block; font-size: 10px; color: var(--text-muted); margin-top: 2px; }
.rmse-excellent { color: #059669; }
.rmse-good { color: #D97706; }
.rmse-fair { color: #DC2626; }

/* ═══════════ Heatmap ═══════════ */
.heatmap-bd { padding: 10px !important; }
.heatmap-grid { display: flex; flex-wrap: wrap; gap: 4px; }
.heatmap-cell { width: calc(25% - 3px); aspect-ratio: 1; border-radius: 6px; display: flex; align-items: center; justify-content: center; }
.heatmap-label { font-size: 10px; color: white; font-weight: 500; text-shadow: 0 1px 2px rgba(0,0,0,.3); }
.heatmap-legend { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; font-size: 10px; color: var(--text-muted); }
.heatmap-gradient { flex: 1; height: 6px; margin: 0 8px; border-radius: 3px; background: linear-gradient(to right, #F1F5F9, #60A5FA, #2563EB, #1D4ED8); }

/* ═══════════ Recommendations ═══════════ */
.rec-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #F1F5F9; }
.rec-row:last-child { border-bottom: none; }
.rec-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.rec-info { flex: 1; min-width: 0; }
.rec-name { display: block; font-size: 12px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rec-reason { display: block; font-size: 10px; color: var(--text-muted); }
.rec-pct { font-size: 12px; font-weight: 700; flex-shrink: 0; }

/* ═══════════ EM Fit Results ═══════════ */
.panel-em .em-row { display: flex; align-items: center; gap: 6px; padding: 5px 0; border-bottom: 1px solid #F1F5F9; font-size: 11px; }
.em-name { flex: 1; font-weight: 500; }
.em-params { font-family: monospace; color: var(--text-secondary); }
.em-rmse { font-family: monospace; font-weight: 600; }
.em-rmse.rmse-excellent { color: #059669; }
.em-rmse.rmse-good { color: #D97706; }
.em-rmse.rmse-fair { color: #DC2626; }

/* ═══════════ Demo ═══════════ */
.demo-flow { display: flex; align-items: stretch; gap: 16px; }
.demo-before, .demo-after { flex: 1; text-align: center; }
.demo-label { font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
.demo-concept { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.demo-pct { font-size: 28px; font-weight: 800; font-family: monospace; line-height: 1.2; }
.demo-pct.after { color: var(--primary); }
.demo-delta { font-size: 12px; font-weight: 600; margin-left: 4px; }
.demo-delta.up { color: #059669; }
.demo-delta.down { color: #DC2626; }
.demo-bar { height: 8px; background: #F1F5F9; border-radius: 4px; margin-top: 8px; overflow: hidden; }
.demo-bar-fill { height: 100%; border-radius: 4px; transition: all .4s ease; }
.after-fill { opacity: .8; }
.demo-arrow { display: flex; align-items: center; padding-top: 28px; }
.demo-answer-btns { display: flex; flex-direction: column; gap: 6px; }
.answer-btn { padding: 6px 16px; border: none; border-radius: var(--radius-md); cursor: pointer; font-size: 13px; font-weight: 600; transition: all .15s; }
.answer-btn.correct { background: #DCFCE7; color: #166534; }
.answer-btn.correct:hover { background: #BBF7D0; }
.answer-btn.wrong { background: #FEE2E2; color: #991B1B; }
.answer-btn.wrong:hover { background: #FECACA; }
.demo-explanation { margin-top: 12px; padding: 10px 14px; background: #EFF6FF; border-radius: var(--radius-md); font-size: 12px; line-height: 1.6; color: #1E40AF; }

/* Step detail table */
.step-detail-header { font-size: 12px; font-weight: 600; margin: 8px 0 4px; color: var(--text-secondary); }
.step-table { width: 100%; border-collapse: collapse; font-size: 11px; font-family: monospace; }
.step-table td { padding: 4px 6px; border-bottom: 1px solid #F1F5F9; color: var(--text-secondary); }
.step-table td:last-child { color: var(--text-primary); font-weight: 600; }

/* ═══════════ Weak Points ═══════════ */
.weak-row { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #F1F5F9; }
.weak-status { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.weak-status.high { background: #EF4444; }
.weak-status.medium { background: #F59E0B; }
.weak-info { flex: 1; min-width: 0; }
.weak-name { display: block; font-size: 12px; font-weight: 500; }
.weak-reason { display: block; font-size: 10px; color: var(--text-muted); }
.weak-action { font-size: 11px; color: var(--primary); cursor: pointer; font-weight: 600; flex-shrink: 0; }

/* Responsive */
@media (max-width: 1024px) {
  .bkt-right { display: none; }
  .bkt-left { width: 240px; }
}
</style>
