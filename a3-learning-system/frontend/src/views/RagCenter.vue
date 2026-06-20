<template>
  <div class="rag">
    <!-- Search bar (inline, no redundant header) -->
    <div class="rag-bar">
      <div class="rag-bar-l">
        <h1>RAG Explainability Center</h1>
        <p>Dense(BGE-M3) + BM25(jieba) → RRF 融合 → CrossEncoder 精排 → LLM 生成</p>
      </div>
      <div class="rag-bar-r">
        <el-input v-model="q" placeholder="输入查询..." size="default" style="width:260px" @keydown.enter="search" clearable :disabled="ld" />
        <el-button type="primary" @click="search" :loading="ld">{{ ld ? progressText : '执行追踪' }}</el-button>
        <el-select v-model="preset" size="default" style="width:150px" placeholder="示例" @change="q=preset;search()" :disabled="ld">
          <el-option v-for="p in presets" :key="p" :label="p" :value="p" />
        </el-select>
      </div>
    </div>

    <!-- Progress -->
    <div v-if="ld" class="rag-progress">
      <div class="rp-bar"><div class="rp-fill" :style="{ width: progressPct + '%' }" /></div>
      <span class="rp-text">{{ progressText }}</span>
    </div>

    <!-- Error -->
    <div v-if="errMsg && !ld" class="rag-err"><el-icon><WarningFilled /></el-icon> {{ errMsg }}</div>

    <!-- Not logged in -->
    <div v-if="!loggedIn" class="rag-empty">
      <el-icon :size="40" color="#CBD5E1"><User /></el-icon>
      <p>请先登录后使用 RAG 检索追踪</p>
      <el-button type="primary" @click="$router.push('/login')">前往登录</el-button>
    </div>

    <!-- Trace View -->
    <div v-else-if="trace.length" class="rag-body">
      <!-- Stats -->
      <div class="rag-stats">
        <div class="rs-item"><span class="rs-v">{{ kb }}</span><span class="rs-l">知识库 chunks</span></div>
        <div class="rs-item"><span class="rs-v">{{ ms }}ms</span><span class="rs-l">总耗时</span></div>
        <div class="rs-item"><span class="rs-v">{{ improvement }}</span><span class="rs-l">精排提升</span></div>
        <div class="rs-item"><span class="rs-v">{{ re.length }}</span><span class="rs-l">最终结果</span></div>
        <div class="rs-item"><span class="rs-v" style="color:#8B5CF6">{{ hitRate }}</span><span class="rs-l">Top-3 命中率</span></div>
      </div>

      <div class="rag-main">
        <!-- Left: Timeline -->
        <div class="rag-timeline">
          <div v-for="(s,i) in trace" :key="s.id" class="rt-node" :class="{ done: s.show, current: s.show && exp===s.id }">
            <div class="rt-line" />
            <div class="rt-dot" :class="{ on: s.show }" :style="{ background: s.show?s.color:'#E2E8F0' }">{{ i+1 }}</div>
            <div class="rt-card" @click="exp = exp===s.id ? null : s.id">
              <div class="rt-hd">
                <el-icon :size="15" :color="s.color"><component :is="s.icon" /></el-icon>
                <span class="rt-name">{{ s.name }}</span>
                <span class="rt-badge" :style="{background:s.badgeBg,color:s.color}">{{ s.count }} 条</span>
                <span class="rt-time">{{ s.timeMs }}ms</span>
                <el-icon :size="14" class="rt-chev" :class="{open:exp===s.id}"><ArrowDown /></el-icon>
              </div>
              <div class="rt-score-bar">
                <div class="rt-score-fill" :style="{width:(s.stats.avg*100)+'%',background:s.color}" />
                <span class="rt-score-txt">avg {{ (s.stats.avg*100).toFixed(0) }}% / max {{ (s.stats.max*100).toFixed(0) }}%</span>
              </div>
              <div class="rt-desc">{{ s.desc }}</div>
              <div v-if="exp===s.id" class="rt-expand">
                <div class="rte-stats">
                  <div class="rte-s"><span>{{ (s.stats.avg*100).toFixed(1) }}%</span><small>平均</small></div>
                  <div class="rte-s"><span>{{ (s.stats.max*100).toFixed(1) }}%</span><small>最高</small></div>
                  <div class="rte-s"><span>{{ (s.stats.top3_avg*100).toFixed(1) }}%</span><small>Top-3</small></div>
                  <div class="rte-s"><span>{{ s.timeMs }}ms</span><small>耗时</small></div>
                </div>
                <div class="rte-list">
                  <div v-for="(r,ri) in s.results.slice(0,8)" :key="ri" class="rte-row">
                    <span class="rte-n">#{{ ri+1 }}</span>
                    <div class="rte-bar-w"><div class="rte-bar" :style="{width:(r.score*100)+'%',background:s.color}" /></div>
                    <span class="rte-sc">{{ (r.score*100).toFixed(1) }}%</span>
                    <span class="rte-tx">{{ r.content.slice(0,90) }}...</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <!-- LLM Stage -->
          <div class="rt-node done">
            <div class="rt-line" />
            <div class="rt-dot" style="background:#8B5CF6">5</div>
            <div class="rt-card">
              <div class="rt-hd"><el-icon :size="15" color="#8B5CF6"><Cpu /></el-icon> <span class="rt-name">LLM 生成</span><span class="rt-badge" style="background:rgba(139,92,246,.08);color:#8B5CF6">Top-{{ re.length }}</span></div>
              <div class="rt-desc">注入精排 Top-{{ Math.min(3, re.length) }} 文档块到 Prompt → 讯飞星火 4.0Ultra 生成最终回答</div>
            </div>
          </div>
        </div>

        <!-- Right: Charts -->
        <div class="rag-right">
          <div class="rr-chart">
            <div class="rr-tt">各阶段分数演变 — 量化精排提升</div>
            <div ref="chartRef" style="height:280px" />
          </div>
          <div class="rr-hit">
            <div class="rr-tt">检索命中率对比 (Top-1 ≥ 80%)</div>
            <div class="rr-hit-grid">
              <div class="rr-hit-card"><span class="rhc-v">Dense</span><span class="rhc-p">{{ denseHitRate }}</span></div>
              <div class="rr-hit-card"><span class="rhc-v">BM25</span><span class="rhc-p">{{ bm25HitRate }}</span></div>
              <div class="rr-hit-card hl"><span class="rhc-v">Reranked</span><span class="rhc-p">{{ rerankHitRate }}</span></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty (logged in, no search yet) -->
    <div v-else-if="loggedIn && !ld && !errMsg" class="rag-empty">
      <el-icon :size="40" color="#CBD5E1"><Search /></el-icon>
      <p>输入查询关键词或选择示例，追踪完整 RAG 检索流水线</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import * as echarts from 'echarts'
import api from '@/api/index'
import { useChatStore } from '@/stores/chat'

const cs = useChatStore()
const q = ref('')
const preset = ref('')
const ld = ref(false)
const exp = ref<string|null>(null)
const chartRef = ref<HTMLElement>()
const errMsg = ref('')
const loggedIn = ref(!!localStorage.getItem('token'))
const progressPct = ref(0)
const progressText = ref('')

const presets = ['Python装饰器','面向对象','二分查找','TCP三次握手','机器学习过拟合','B+树索引']

interface R { content: string; score: number }
interface Stage { id: string; name: string; icon: string; color: string; badgeBg: string; desc: string; show: boolean; count: number; timeMs: number; stats: {min:number;max:number;avg:number;top3_avg:number}; results: R[] }
const trace = ref<Stage[]>([])
const re = ref<R[]>([])
const kb = ref(0); const ms = ref(0); const improvement = ref('—')

const hitRate = computed(() => re.value.filter(r=>r.score>=.8).length + '/' + re.value.length)
const denseHitRate = computed(() => trace.value[0]?.stats?.max >= .8 ? '✓' : '✗')
const bm25HitRate = computed(() => trace.value[1]?.stats?.max >= .8 ? '✓' : '✗')
const rerankHitRate = computed(() => re.value.filter(r=>r.score>=.8).length + '/' + re.value.length)

async function search() {
  if (!q.value.trim() || ld.value) return
  ld.value = true; exp.value = null; errMsg.value = ''; trace.value = []; re.value = []
  progressPct.value = 5; progressText.value = '正在 Embedding 查询向量...'

  try {
    const r = await api.get('/admin/rag-trace', { params: { query: q.value.trim() } })
    progressPct.value = 80; progressText.value = '处理响应数据...'
    const d = r.data
    kb.value = d.kb_total || 0; ms.value = d.latency_ms || 0
    improvement.value = d.improvement?.description || '—'
    re.value = (d.pipeline?.reranked || []).map((x:any)=>({content:x.content||'',score:x.score||0}))

    const colors: Record<string,string> = { dense:'#2563EB', bm25:'#10B981', rrf:'#F59E0B', rerank:'#8B5CF6' }
    const icons: Record<string,string> = { dense:'Connection', bm25:'Search', rrf:'Operation', rerank:'TrendCharts' }
    const descs: Record<string,string> = {
      dense:'BGE-M3 Embedding → FAISS 向量检索 → Top-10 语义相似文档',
      bm25:'jieba 中文分词 → TF-IDF BM25 算法 → Top-10 关键词匹配',
      rrf:'Reciprocal Rank Fusion (k=60) — 合并两路召回, 去重后按 RRF 分数重排',
      rerank:'BGE-Reranker-v2-m3 CrossEncoder — 逐对(query,doc)打分, 输出最终 Top-5',
    }
    const bgColors: Record<string,string> = { dense:'rgba(37,99,235,.08)', bm25:'rgba(16,185,129,.08)', rrf:'rgba(245,158,11,.08)', rerank:'rgba(139,92,246,.08)' }
    const rm: Record<string,R[]> = {
      dense: (d.pipeline?.dense_recall||[]).map((x:any)=>({content:x.content,score:x.score})),
      bm25: (d.pipeline?.bm25_recall||[]).map((x:any)=>({content:x.content,score:x.score})),
      rrf: (d.pipeline?.rrf_fused||[]).map((x:any)=>({content:x.content,score:x.score})),
      rerank: (d.pipeline?.reranked||[]).map((x:any)=>({content:x.content,score:x.score})),
    }
    trace.value = (d.stage_summary||[]).map((s:any) => ({
      id:s.id, name:s.name, icon:icons[s.id]||'Connection', color:colors[s.id]||'#64748B',
      badgeBg:bgColors[s.id]||'', desc:descs[s.id]||'', show:false,
      count:s.count||0, timeMs:s.time_ms||0, stats:s.stats||{min:0,max:0,avg:0,top3_avg:0},
      results:rm[s.id]||[],
    }))

    progressPct.value = 95; progressText.value = '渲染结果...'
    for (let i=0;i<trace.value.length;i++) {
      await new Promise(r=>setTimeout(r,300))
      trace.value[i] = {...trace.value[i], show:true}
    }
    exp.value = 'rerank'
    errMsg.value = ''
    // 持久化本次检索结果
    localStorage.setItem('rag_last_trace', JSON.stringify({
      query: q.value, trace: trace.value, re: re.value,
      kb: kb.value, ms: ms.value, improvement: improvement.value,
    }))
    nextTick(()=>renderChart())
  } catch(e:any){
    errMsg.value = e?.response?.data?.detail || e?.message || '请求失败'
    if (e?.response?.status === 401) { loggedIn.value = false; localStorage.removeItem('token') }
    trace.value = []; re.value = []
  }
  ld.value = false; progressPct.value = 100
}

function renderChart() {
  if (!chartRef.value || re.value.length < 2) return
  const c = echarts.init(chartRef.value)
  const top = re.value.slice(0,5)
  c.setOption({
    tooltip:{trigger:'axis'},
    legend:{data:['Dense','BM25','RRF','Reranked'],bottom:0,textStyle:{fontSize:11}},
    grid:{top:10,right:30,bottom:35,left:50},
    xAxis:{type:'category',data:top.map((_,i)=>'#'+(i+1)),axisLabel:{fontSize:12}},
    yAxis:{type:'value',name:'分数',max:100,axisLabel:{fontSize:11,formatter:'{value}%'}},
    series:[
      {name:'Dense',type:'line',smooth:true,data:top.map((_,i)=>+(trace.value[0]?.results[i]?.score*100||0).toFixed(1)),lineStyle:{color:'#2563EB',width:2},itemStyle:{color:'#2563EB'},symbol:'circle',symbolSize:6},
      {name:'BM25',type:'line',smooth:true,data:top.map((_,i)=>+(trace.value[1]?.results[i]?.score*100||0).toFixed(1)),lineStyle:{color:'#10B981',width:2},itemStyle:{color:'#10B981'},symbol:'diamond',symbolSize:6},
      {name:'RRF',type:'line',smooth:true,data:top.map((_,i)=>+(trace.value[2]?.results[i]?.score*100||0).toFixed(1)),lineStyle:{color:'#F59E0B',width:1.5,type:'dashed'},itemStyle:{color:'#F59E0B'},symbol:'triangle',symbolSize:6},
      {name:'Reranked',type:'line',smooth:true,data:top.map(r=>+(r.score*100).toFixed(1)),lineStyle:{color:'#8B5CF6',width:3},itemStyle:{color:'#8B5CF6'},symbol:'roundRect',symbolSize:8,areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(139,92,246,.15)'},{offset:1,color:'rgba(139,92,246,0)'}]}}},
    ],
  })
}

onMounted(()=>{
  if (!localStorage.getItem('token')) { loggedIn.value = false; return }
  // 恢复上次检索结果
  const saved = localStorage.getItem('rag_last_trace')
  if (saved) {
    try {
      const d = JSON.parse(saved)
      q.value = d.query || ''
      trace.value = (d.trace || []).map((s:any)=>({...s, show:true}))  // 恢复时直接显示
      re.value = d.re || []
      kb.value = d.kb || 0; ms.value = d.ms || 0
      improvement.value = d.improvement || '—'
      exp.value = 'rerank'
      nextTick(()=>renderChart())
      return  // 已有缓存数据，不自动重新搜索
    } catch {}
  }
  // 无缓存时自动搜索最近对话
  const m=[...cs.messages].reverse().find(x=>x.role==='user')
  if(m){ q.value=m.content.slice(0,80); search() }
})
</script>

<style scoped>
.rag{height:100%;display:flex;flex-direction:column;overflow:hidden}

.rag-bar{display:flex;align-items:flex-start;justify-content:space-between;padding:20px 24px 14px;flex-shrink:0}
.rag-bar-l h1{font-size:var(--font-xl);font-weight:700}
.rag-bar-l p{font-size:var(--font-sm);color:var(--text-secondary);margin-top:3px}
.rag-bar-r{display:flex;gap:10px;align-items:center}

.rag-progress{display:flex;align-items:center;gap:10px;padding:0 24px 8px;flex-shrink:0}
.rp-bar{flex:1;height:4px;background:#F1F5F9;border-radius:2px;overflow:hidden}
.rp-fill{height:100%;background:#2563EB;border-radius:2px;transition:width .3s}
.rp-text{font-size:var(--font-xs);color:var(--text-muted);white-space:nowrap}
.rag-err{padding:8px 24px;font-size:var(--font-xs);color:#EF4444;display:flex;align-items:center;gap:6px}
.rag-empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:var(--text-muted)}

.rag-body{flex:1;overflow-y:auto;display:flex;flex-direction:column;padding:0 24px 20px}

.rag-stats{display:flex;gap:0;padding:8px 0 14px;flex-shrink:0}
.rs-item{flex:1;text-align:center}
.rs-v{font-size:18px;font-weight:700;display:block}
.rs-l{font-size:10px;color:var(--text-muted);margin-top:2px}

.rag-main{flex:1;display:flex;overflow:hidden}
.rag-timeline{flex:1;overflow-y:auto;padding-right:12px;position:relative}
.rag-right{width:380px;flex-shrink:0;overflow-y:auto;display:flex;flex-direction:column;gap:14px}

.rt-node{position:relative;padding-bottom:12px}
.rt-node:last-child{padding-bottom:0}
.rt-line{position:absolute;left:15px;top:28px;bottom:0;width:2px;background:#E2E8F0}
.rt-node.done .rt-line{background:#2563EB}
.rt-node:last-child .rt-line{display:none}
.rt-dot{position:absolute;left:8px;top:10px;width:16px;height:16px;border-radius:50%;background:#E2E8F0;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#fff;transition:all .3s}
.rt-dot.on{width:22px;height:22px;left:5px;top:7px;font-size:12px}

.rt-card{margin-left:32px;background:var(--bg-card);border:1.5px solid var(--border);border-radius:10px;overflow:hidden;cursor:pointer;transition:all .2s}
.rt-card:hover{border-color:#93C5FD}
.rt-node.current .rt-card{border-color:#2563EB;box-shadow:0 0 10px rgba(37,99,235,.06)}
.rt-hd{display:flex;align-items:center;gap:8px;padding:10px 14px}
.rt-name{font-size:var(--font-sm);font-weight:600;flex:1}
.rt-badge{font-size:11px;padding:2px 10px;border-radius:12px;font-weight:600}
.rt-time{font-size:var(--font-xs);color:var(--text-muted)}
.rt-chev{color:var(--text-muted);transition:transform .2s}
.rt-chev.open{transform:rotate(180deg)}
.rt-desc{font-size:var(--font-xs);color:var(--text-muted);padding:0 14px 8px}
.rt-score-bar{display:flex;align-items:center;gap:6px;padding:0 14px 6px}
.rt-score-fill{height:4px;border-radius:2px;min-width:2px;flex:1}
.rt-score-txt{font-size:10px;color:var(--text-muted);white-space:nowrap}

.rt-expand{border-top:1px solid var(--border);padding:10px 14px}
.rte-stats{display:flex;gap:14px;margin-bottom:8px}
.rte-s{display:flex;flex-direction:column}
.rte-s span{font-size:15px;font-weight:700;color:var(--primary)}
.rte-s small{font-size:10px;color:var(--text-muted)}
.rte-list{display:flex;flex-direction:column;gap:4px}
.rte-row{display:flex;align-items:center;gap:8px}
.rte-n{font-size:11px;font-weight:700;color:var(--text-muted);width:20px}
.rte-bar-w{flex:1;height:5px;background:#F1F5F9;border-radius:3px;overflow:hidden}
.rte-bar{height:100%;border-radius:3px;transition:width .6s}
.rte-sc{font-size:12px;font-weight:700;width:44px;text-align:right}
.rte-tx{font-size:11px;color:var(--text-secondary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

.rr-chart{background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:14px}
.rr-tt{font-size:var(--font-sm);font-weight:600;margin-bottom:6px}
.rr-hit{background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:14px}
.rr-hit-grid{display:flex;gap:8px;margin-top:6px}
.rr-hit-card{flex:1;text-align:center;padding:10px 8px;border-radius:8px;background:var(--bg-page)}
.rr-hit-card.hl{background:rgba(139,92,246,.06);border:1px solid rgba(139,92,246,.2)}
.rhc-v{font-size:var(--font-xs);color:var(--text-muted);display:block}
.rhc-p{font-size:22px;font-weight:700;display:block;margin:4px 0}
</style>
