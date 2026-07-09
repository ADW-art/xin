<!--
ResourceDetail 资源详情页

作用：
  展示单个资源的完整内容，根据资源类型使用不同的渲染方式
  五种资源类型：document(文档) / mindmap(思维导图) / code_example(代码示例) / question_set(练习题集) / video_script(视频脚本)

关联文件：
  router/index.ts              ← /resources/:id 路由指向本页
  views/ResourceView.vue       ← 资源列表页，点击卡片跳转到本页
  components/resource/MindMap.vue ← 思维导图渲染组件
  api/resource.ts              ← getResource() 获取资源详情

路由参数：
  :id — 资源ID，用于从 API 获取完整资源数据
-->
<template>
  <div class="page">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading a-fade">
      <el-icon class="spin"><Loading/></el-icon>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-state a-scale">
      <svg viewBox="0 0 200 120" class="err-svg">
        <rect x="55" y="18" width="90" height="60" rx="10" fill="rgba(248,113,113,.08)" stroke="rgba(248,113,113,.2)" stroke-width="1.8"/>
        <circle cx="100" cy="48" r="14" fill="rgba(248,113,113,.12)" stroke="rgba(248,113,113,.25)" stroke-width="1.2"/>
        <path d="M94 42l12 12M106 42l-12 12" stroke="#DC2626" stroke-width="2" stroke-linecap="round"/>
        <rect x="72" y="86" width="56" height="5" rx="2.5" fill="rgba(255,255,255,.05)"/>
        <rect x="80" y="96" width="40" height="4" rx="2" fill="rgba(255,255,255,.04)"/>
      </svg>
      <h3>{{ error }}</h3>
      <el-button type="primary" @click="$router.push('/resources')">
        <el-icon><ArrowLeft/></el-icon> 返回资源列表
      </el-button>
    </div>

    <!-- 空状态：资源不存在 (加载完成但resource为null) -->
    <div v-else-if="!loading && !error && !resource" class="error-state a-scale">
      <svg viewBox="0 0 200 120" class="err-svg" xmlns="http://www.w3.org/2000/svg">
        <rect x="55" y="18" width="90" height="60" rx="10" fill="rgba(148,163,184,.08)" stroke="rgba(148,163,184,.2)" stroke-width="1.8"/>
        <circle cx="100" cy="48" r="14" fill="rgba(148,163,184,.12)" stroke="rgba(148,163,184,.25)" stroke-width="1.2"/>
        <line x1="100" y1="38" x2="100" y2="58" stroke="#94A3B8" stroke-width="2" stroke-linecap="round"/>
        <line x1="90" y1="48" x2="110" y2="48" stroke="#94A3B8" stroke-width="2" stroke-linecap="round"/>
        <rect x="72" y="86" width="56" height="5" rx="2.5" fill="rgba(148,163,184,.06)"/>
        <rect x="80" y="96" width="40" height="4" rx="2" fill="rgba(148,163,184,.05)"/>
      </svg>
      <h3>资源不存在或已被删除</h3>
      <el-button type="primary" @click="$router.push('/resources')">
        <el-icon><ArrowLeft/></el-icon> 返回资源列表
      </el-button>
    </div>

    <!-- 资源内容 -->
    <template v-else-if="resource">
      <!-- 顶部导航栏 -->
      <div class="detail-header a-slide">
        <el-button text class="back-btn" @click="$router.push('/resources')">
          <el-icon><ArrowLeft/></el-icon> 返回资源列表
        </el-button>

        <div class="header-card">
          <!-- 类型标签 + 难度 -->
          <div class="header-row">
            <span class="type-badge" :style="{ background: typeInfo.bg, color: typeInfo.color, borderColor: typeInfo.border }">
              <el-icon :size="14"><component :is="typeInfo.icon"/></el-icon>
              {{ typeInfo.label }}
            </span>
            <span v-if="resource.difficulty_level" class="difficulty">
              <span v-for="n in 5" :key="n" class="dot" :class="{ active: n <= (resource.difficulty_level || 0) }" :style="n <= (resource.difficulty_level || 0) ? { background: typeInfo.color } : {}"/>
              <span class="diff-label">难度 {{ resource.difficulty_level }}/5</span>
            </span>
          </div>

          <h1 class="resource-title">{{ resource.title }}</h1>

          <div class="header-meta">
            <span v-if="resource.generated_by" class="meta-item">
              <el-icon :size="13"><Cpu/></el-icon> {{ resource.generated_by }}
            </span>
            <span v-if="resource.created_at" class="meta-item">
              <el-icon :size="13"><Clock/></el-icon> {{ formatDate(resource.created_at) }}
            </span>
            <span v-if="resource.knowledge_points?.length" class="meta-item kp">
              <el-icon :size="13"><CollectionTag/></el-icon> {{ resource.knowledge_points.join(' · ') }}
            </span>
          </div>

          <!-- 视频讲解按钮 (仅文档和视频脚本类型) -->
          <div v-if="isSlideshowType" class="header-actions">
            <el-button
              :type="showSlidePlayer ? 'default' : 'primary'"
              size="default"
              @click="showSlidePlayer = !showSlidePlayer; autoPlaySlides = !showSlidePlayer"
            >
              <el-icon :size="14"><VideoPlay /></el-icon>
              {{ showSlidePlayer ? '收起讲解' : '视频讲解' }}
            </el-button>
          </div>
        </div>
      </div>

      <!-- 内容区域 (按类型渲染) -->
      <div class="content-card a-fade-up">
        <!-- document / question_set / video_script → Markdown 渲染 -->
        <div v-if="isMarkdownType" class="markdown-body" v-html="renderedMarkdown"/>

        <!-- mindmap → MindMap 组件 -->
        <MindMap v-else-if="resource.resource_type === 'mindmap'" :content="resource.content || ''" height="600px"/>

        <!-- code_example → 代码块 -->
        <div v-else-if="resource.resource_type === 'code_example'" class="code-section">
          <div class="code-toolbar">
            <span class="code-lang-label">Code</span>
            <el-button text size="small" @click="copyCode">
              <el-icon :size="14"><DocumentCopy/></el-icon> {{ copyLabel }}
            </el-button>
          </div>
          <pre class="code-block"><code>{{ resource.content }}</code></pre>
        </div>

        <!-- 未知类型兜底 -->
        <div v-else class="markdown-body" v-html="renderedMarkdown"/>
      </div>

      <!-- 视频讲解幻灯片 (仅文档和视频脚本类型) -->
      <SlidePlayer
        v-if="isSlideshowType"
        v-model:visible="showSlidePlayer"
        :content="resource.content || ''"
        :auto-play="autoPlaySlides"
      />

      <!-- 评分反馈区域 -->
      <div class="rating-card a-fade-up">
        <div class="rating-header">
          <span class="rating-title">
            <el-icon :size="16"><StarFilled v-if="currentRating" style="color: #F59E0B;"/><Star v-else/></el-icon>
            {{ currentRating ? `已评分: ${currentRating}/5` : '评分' }}
          </span>
          <span class="rating-hint">为此资源打分，帮助我们改进推荐</span>
        </div>
        <el-rate
          v-model="currentRating"
          :max="5"
          :disabled="ratingLoading"
          :clearable="false"
          show-score
          score-template="{value}/5"
          @change="handleRate"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, type Component } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import { ElMessage } from 'element-plus'
import DOMPurify from 'dompurify'
import { ArrowLeft, Loading, Document, Connection, DocumentCopy, EditPen, VideoCamera, VideoPlay, Cpu, Clock, CollectionTag, Star, StarFilled } from '@element-plus/icons-vue'
import MindMap from '@/components/resource/MindMap.vue'
import SlidePlayer from '@/components/resource/SlidePlayer.vue'
import { getResource, submitFeedback, type ResourceDetail as ResourceDetailType } from '@/api/resource'

const route = useRoute()

// ── 响应式状态 ──
const loading = ref(true)
const error = ref('')
const resource = ref<ResourceDetailType | null>(null)
const copyLabel = ref('复制代码')
const ratingLoading = ref(false)
const currentRating = ref<number | null>(null)  // displayed rating — starts from resource.feedback_score

// ── 视频讲解幻灯片 ──
const showSlidePlayer = ref(route.query.mode === 'slideshow')
const autoPlaySlides = ref(route.query.mode === 'slideshow')

// ── 类型映射 ──
const typeMap: Record<string, { label: string; icon: Component; bg: string; color: string; border: string }> = {
  document:     { label: '文档',     icon: Document,     bg: 'rgba(37,99,235,.12)', color: '#2563EB', border: 'rgba(37,99,235,.25)' },
  mindmap:      { label: '思维导图', icon: Connection,   bg: 'rgba(59,130,246,.12)', color: '#3B82F6', border: 'rgba(59,130,246,.25)' },
  code_example: { label: '代码示例', icon: DocumentCopy, bg: 'rgba(99,102,241,.12)', color: '#6366F1', border: 'rgba(99,102,241,.25)' },
  question_set: { label: '练习题集', icon: EditPen,     bg: 'rgba(14,165,233,.12)', color: '#0EA5E9', border: 'rgba(14,165,233,.25)' },
  video_script: { label: '视频脚本', icon: VideoCamera,  bg: 'rgba(96,165,250,.15)', color: '#60A5FA', border: 'rgba(96,165,250,.30)' },
}

// ─� 计算属性 ──
const typeInfo = computed(() => {
  return typeMap[resource.value?.resource_type || ''] || typeMap.document
})

const isMarkdownType = computed(() => {
  const t = resource.value?.resource_type
  return t === 'document' || t === 'question_set' || t === 'video_script'
})

// 仅文档和视频脚本资源支持视频讲解幻灯片
const isSlideshowType = computed(() => {
  const t = resource.value?.resource_type
  return t === 'document' || t === 'video_script'
})

const renderedMarkdown = computed(() => {
  const content = resource.value?.content || ''
  let html = ''
  try {
    html = DOMPurify.sanitize(marked.parse(content) as string, { ALLOWED_ATTR: ['class', 'href', 'target', 'id', 'style'], ALLOWED_TAGS: ['a', 'b', 'i', 'em', 'strong', 'p', 'br', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'code', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'img', 'span', 'div'] })
  } catch {
    html = content.replace(/</g, '&lt;').replace(/>/g, '&gt;')
  }
  // 视频脚本：为时间戳添加样式
  if (resource.value?.resource_type === 'video_script') {
    html = html.replace(/(\d{1,2}:\d{2}(?::\d{2})?)/g, '<span class="timestamp">$1</span>')
  }
  return html
})

// ── 工具方法 ──
function formatDate(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

async function copyCode() {
  const code = resource.value?.content || ''
  try {
    await navigator.clipboard.writeText(code)
    copyLabel.value = '已复制'
    setTimeout(() => { copyLabel.value = '复制代码' }, 1800)
  } catch {
    ElMessage.warning('复制失败，请手动选择')
  }
}

async function handleRate(score: number) {
  if (!resource.value || ratingLoading.value) return
  ratingLoading.value = true
  try {
    const result = await submitFeedback(resource.value.id, score)
    currentRating.value = result.feedback_score
    ElMessage.success('评分已提交')
  } catch {
    ElMessage.error('评分提交失败，请稍后重试')
  } finally {
    ratingLoading.value = false
  }
}

// ── 加载资源详情 ──
onMounted(async () => {
  const id = Number(route.params.id)
  if (!id || isNaN(id)) {
    error.value = '无效的资源 ID'
    loading.value = false
    return
  }
  try {
    const detail = await getResource(id)
    if (!detail) {
      error.value = '资源未找到'
    } else {
      resource.value = detail
      currentRating.value = detail.feedback_score ?? null
    }
  } catch (err: unknown) {
    const e = err as { response?: { status?: number } }
    if (e?.response?.status === 404) {
      error.value = '资源未找到'
    } else {
      error.value = '加载资源失败，请稍后重试'
    }
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
/* ── 页面容器 ── */
.page { max-width: 960px; margin: 0 auto; padding: 28px 28px 48px }

/* ── 加载 & 错误 ── */
.loading { display: flex; justify-content: center; padding: 80px 0; color: var(--text-secondary) }
.spin { animation: spin 1s linear infinite }
@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }

.error-state { text-align: center; padding: 60px 0 }
.err-svg { width: 180px; height: 110px; margin-bottom: 16px; opacity: .6 }
.error-state h3 { font-size: var(--font-lg); font-weight: 500; color: var(--text-secondary); margin-bottom: 16px }

/* ── 详情头部 ── */
.detail-header { margin-bottom: 20px }
.back-btn { color: var(--text-secondary); margin-bottom: 14px; transition: color var(--transition-fast) }
.back-btn:hover { color: var(--primary-hover) }

.header-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 24px 26px;
}

.header-row { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; flex-wrap: wrap }

.type-badge { display: inline-flex; align-items: center; gap: 5px; padding: 4px 12px; border-radius: var(--radius-xl); font-size: var(--font-xs); font-weight: 600; border: 1px solid }

.difficulty { display: flex; align-items: center; gap: 4px }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--border); transition: all var(--transition-fast) }
.dot.active { transform: scale(1.15) }
.diff-label { font-size: var(--font-xs); color: var(--text-muted); margin-left: 6px }

.resource-title { font-size: var(--font-2xl); font-weight: 700; line-height: 1.3; margin-bottom: 12px; color: var(--text-primary); }

.header-meta { display: flex; flex-wrap: wrap; gap: 16px; font-size: var(--font-xs); color: var(--text-secondary); align-items: center }
.meta-item { display: inline-flex; align-items: center; gap: 4px }
.kp { color: var(--primary); font-weight: 500 }

/* ── 视频讲解按钮 ── */
.header-actions {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  gap: 10px;
}

/* ── 内容卡片 ── */
.content-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 28px 30px;
}

/* ── Markdown 内容 ── */
.markdown-body { line-height: 1.85; color: var(--text-primary) }
.markdown-body :deep(h1) { font-size: var(--font-2xl); font-weight: 700; margin: 28px 0 14px; padding-bottom: 8px; border-bottom: 1px solid var(--border); color: var(--text-primary) }
.markdown-body :deep(h2) { font-size: var(--font-xl); font-weight: 700; margin: 24px 0 12px; color: var(--text-primary) }
.markdown-body :deep(h3) { font-size: var(--font-lg); font-weight: 600; margin: 20px 0 10px; color: var(--text-primary) }
.markdown-body :deep(h4) { font-size: var(--font-base); font-weight: 600; margin: 16px 0 8px }
.markdown-body :deep(p) { margin: 10px 0 }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 22px; margin: 8px 0 }
.markdown-body :deep(li) { margin: 4px 0 }
.markdown-body :deep(a) { color: var(--primary); text-decoration: none }
.markdown-body :deep(a:hover) { text-decoration: underline }
.markdown-body :deep(blockquote) { border-left: 3px solid var(--primary); padding: 6px 14px; margin: 12px 0; background: var(--primary-light); border-radius: 0 var(--radius-md) var(--radius-md) 0; color: var(--text-secondary) }
.markdown-body :deep(code) { background: var(--bg-muted); color: var(--text-primary); padding: 2px 6px; border-radius: var(--radius-sm); font-size: 13px; font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace }
.markdown-body :deep(pre) { background: #1E293B; color: #E2E8F0; border-radius: var(--radius-md); padding: 18px 20px; overflow-x: auto; margin: 14px 0; border: 1px solid #334155 }
.markdown-body :deep(pre code) { background: none; padding: 0; font-size: var(--font-sm); line-height: 1.65 }
.markdown-body :deep(table) { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: var(--font-sm) }
.markdown-body :deep(th) { background: var(--bg-page); padding: 10px 14px; text-align: left; font-weight: 600; border-bottom: 2px solid var(--border); color: var(--text-secondary) }
.markdown-body :deep(td) { padding: 10px 14px; border-bottom: 1px solid var(--border) }
.markdown-body :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 20px 0 }
.markdown-body :deep(strong) { font-weight: 700; color: var(--text-primary) }
.markdown-body :deep(img) { max-width: 100%; border-radius: var(--radius-md) }

/* 时间戳样式 (video_script) */
.markdown-body :deep(.timestamp) {
  display: inline-block;
  background: rgba(6,182,212,.1);
  color: var(--cyan);
  font-weight: 600;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-size: var(--font-xs);
  margin: 0 2px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  border: 1px solid rgba(6,182,212,.2);
}

/* ── 代码块 ── */
.code-section { border-radius: var(--radius-md); overflow: hidden; border: 1px solid #334155 }
.code-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; background: #0F172A; border-bottom: 1px solid #334155 }
.code-lang-label { font-size: var(--font-xs); color: var(--text-muted); font-weight: 600; text-transform: uppercase; letter-spacing: .8px }
.code-toolbar .el-button { color: var(--text-muted); font-size: var(--font-xs) }
.code-toolbar .el-button:hover { color: #E2E8F0 }

.code-block { background: #1E293B; color: #E2E8F0; padding: 20px 22px; margin: 0; overflow-x: auto; font-size: var(--font-sm); line-height: 1.7; font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace; white-space: pre; tab-size: 4; border-radius: 0 0 var(--radius-md) var(--radius-md) }
.code-block code { font-family: inherit }

/* ── 评分卡片 ── */
.rating-card {
  margin-top: 20px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px 26px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.rating-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.rating-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--font-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.rating-hint {
  font-size: var(--font-xs);
  color: var(--text-muted);
}

/* ═══════════ Responsive ═══════════ */
@media (max-width: 768px) {
  .page { padding: 20px 16px 36px; max-width: 100%; }
  .header-card { padding: 18px 20px; }
  .resource-title { font-size: 18px; }
  .content-card { padding: 20px 22px; }
  .rating-card { padding: 16px 20px; flex-direction: column; align-items: flex-start; gap: 12px; }
  .code-block { padding: 16px; font-size: 12px; }
  .header-meta { gap: 10px; }
}

@media (max-width: 480px) {
  .page { padding: 12px 10px 28px; }
  .detail-header { margin-bottom: 12px; }
  .back-btn { margin-bottom: 8px; font-size: 12px; }
  .header-card { padding: 14px 16px; border-radius: var(--radius-md); }
  .header-row { gap: 8px; margin-bottom: 10px; }
  .resource-title { font-size: 16px; margin-bottom: 8px; }
  .header-meta { gap: 6px; font-size: 10px; }
  .content-card { padding: 14px 16px; border-radius: var(--radius-md); }
  .rating-card { padding: 12px 16px; gap: 8px; }
  .markdown-body { font-size: 13px; line-height: 1.7; }
  .markdown-body :deep(h1) { font-size: 18px; }
  .markdown-body :deep(h2) { font-size: 16px; }
  .markdown-body :deep(h3) { font-size: 14px; }
  .markdown-body :deep(pre) { padding: 12px 14px; }
  .code-block { padding: 12px 14px; font-size: 11px; }
}
</style>
