<template>
  <div :class="['msg', role]">
    <div class="av" :class="role">
      <el-icon :size="18"><component :is="role === 'user' ? 'User' : 'ChatDotRound'" /></el-icon>
    </div>
    <div class="bb" @click="onBubbleClick">
      <!-- Agent switch tag -->
      <div v-if="agentSwitch" class="tag">{{ agentSwitch.from }} &rarr; {{ agentSwitch.to }}</div>

      <!-- Agent header row -->
      <div v-if="agent && role === 'assistant'" class="ah">
        <span class="ah-name">{{ agentLabel(agent) }}</span>
          <span v-if="collabAgents && collabAgents.length > 1" class="collab-badge">&#9889; {{ collabAgents.join(' + ') }}</span>
          <span v-if="collabAgents && collabAgents.length > 1" class="collab-badge">&#9889; ??</span>
        <span v-if="resolvedResourceType" class="ah-badge" :class="resolvedResourceType">
          {{ resourceTypeLabel(resolvedResourceType) }}
        </span>
      </div>

      <!-- Message body + streaming cursor -->
      <div class="body" ref="bodyRef">
        <!-- 多模态：用户消息中的图片 -->
        <div v-if="images && images.length > 0 && role === 'user'" class="msg-images">
          <img
            v-for="(src, idx) in images"
            :key="idx"
            :src="src"
            :alt="'图片'+(idx+1)"
            class="msg-img image-card"
            @click="openLightbox(src)"
          />
        </div>

        <!-- 非流式：按文本/代码段渲染 -->
        <template v-if="!isStreaming && textContent">
          <template v-for="(seg, idx) in contentSegments" :key="idx">
            <div v-if="seg.type === 'text'" v-html="renderMarkdown(seg.content)" class="text-segment" />
            <CodeCard v-else :code="seg.content" :language="seg.language" />
          </template>
        </template>

        <!-- 流式输出：使用原有 computed 渲染 -->
        <div v-else-if="isStreaming" class="streaming-wrap">
          <StreamingText :content="textContent" :speed="20" />
        </div>

        <!-- 空内容占位 -->
        <div v-else-if="!textContent && !isStreaming" class="empty-placeholder">
          <span>暂无内容</span>
        </div>
      </div>

      <!-- Video trigger for video_script type -->
      <div v-if="role === 'assistant' && resolvedResourceType === 'video_script' && !isStreaming" class="video-trigger-row">
        <el-button size="small" type="primary" plain @click="openInlineVideo" :loading="videoLoading" class="video-trigger-btn">
          <el-icon :size="14"><VideoCamera /></el-icon>
          <span>{{ videoLoading ? '生成视频中...' : '播放视频讲解' }}</span>
        </el-button>
      </div>

      <!-- 内容生成预览（resource_ready 到达前显示摘要卡片） -->
      <div v-if="resolvedResourceType && !resourceId && !isStreaming && role === 'assistant'" class="res-preview">
        <div class="res-preview-header">
          <el-icon :size="16"><component :is="resourceIcon" /></el-icon>
          <span class="res-preview-type">{{ resourceTypeLabel(resolvedResourceType) }}</span>
          <el-tag size="small" type="warning" effect="plain">生成中</el-tag>
        </div>
        <p class="res-preview-text">{{ contentPreviewText }}</p>
        <div class="res-preview-progress">
          <div class="res-preview-progress-bar" />
        </div>
      </div>

      <!-- 内嵌资源播放器（不跳转页面） -->
      <div v-if="showInlineSlide" class="inline-player-wrap">
        <SlidePlayer v-if="slideContent" v-model:visible="showInlineSlide" :content="slideContent" :auto-play="true" />
        <div v-else class="inline-player-loading">
          <el-icon class="spin" :size="20"><Loading /></el-icon>
          <span>加载资源中...</span>
        </div>
      </div>

      <!-- 内嵌视频播放器 -->
      <div v-if="showInlineVideo" class="inline-player-wrap">
        <VideoPlayer 
          :video-url="videoUrl" 
          :title="resourceTitle || '视频讲解'"
          @retry="openInlineVideo"
        />
        <div class="inline-player-close">
          <el-button size="small" text @click="showInlineVideo = false">收起视频</el-button>
        </div>
      </div>

      <!-- MindMap inline toggle -->
      <div v-if="showMindMapBtn" class="mindmap-section">
        <el-button size="small" @click="toggleMindMap" :type="showMindMap ? 'default' : 'primary'" plain>
          <el-icon><component :is="showMindMap ? 'ArrowUp' : 'DataBoard'" /></el-icon>
          {{ showMindMap ? '收起思维导图' : '查看思维导图' }}
        </el-button>
        <div v-if="showMindMap" class="inline-mindmap-wrap">
          <MindMap :content="mindMapContent" height="380px" />
        </div>
      </div>

      <!-- Resource preview card (component) -->
      <ResourceCard
        v-if="resourceId && resourceTitle"
        :resource-type="resolvedResourceType || 'document'"
        :resource-title="resourceTitle"
        :resource-id="resourceId"
        :description="resourceDesc"
        :show-slideshow="isSlideshowType"
        @speak="toggleSpeak"
        @slideshow="goToSlideshow"
      />

      <!-- 朗读（TTS 语音合成） -->
      <div v-if="role === 'assistant' && !isStreaming && plainText" class="speak-row">
        <button class="speak-btn" :disabled="ttsLoading" @click="toggleSpeak">
          <el-icon :size="13"><component :is="ttsPlaying ? 'VideoPause' : 'Microphone'" /></el-icon>
          <span>{{ ttsLoading ? '合成中…' : (ttsPlaying ? '停止' : '朗读') }}</span>
        </button>
      </div>
    </div>

    <!-- 图片灯箱 (Teleport 到 body 确保 z-index 正确) -->
    <Teleport to="body">
      <div v-if="lightboxImage" class="lightbox-overlay" @click.self="closeLightbox">
        <button class="lightbox-close" @click="closeLightbox" aria-label="关闭">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
        <img :src="lightboxImage" class="lightbox-img" alt="预览图片" />
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Marked, Renderer } from 'marked'
import DOMPurify from 'dompurify'
import mermaid from 'mermaid'
import MindMap from '@/components/resource/MindMap.vue'
import SlidePlayer from '@/components/resource/SlidePlayer.vue'
import VideoPlayer from '@/components/resource/VideoPlayer.vue'
import CodeCard from '@/components/chat/CodeCard.vue'
import ResourceCard from '@/components/chat/ResourceCard.vue'
import StreamingText from '@/components/chat/StreamingText.vue'
import { ElMessage } from 'element-plus'
import { synthesizeSpeech } from '@/api/tts'
import { getResource } from '@/api/resource'
import api from '@/api'
import { highlightCode, SVG_COPY, SVG_CHECK, safeBtoa, safeAtob } from '@/utils/highlight'

/* ── Mermaid 初始化 ── */
mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  flowchart: { useMaxWidth: true, htmlLabels: true },
  sequence: { useMaxWidth: true },
  gantt: { useMaxWidth: true },
})

const props = defineProps<{
  role: string
  content: string
  images?: string[]
  agent?: string
  agentSwitch?: { from: string; to: string }
  isStreaming?: boolean
  resourceType?: string
  resourceId?: number
  resourceTitle?: string
  collabAgents?: string[]
}>()

const router = useRouter()
const bodyRef = ref<HTMLElement | null>(null)
const showMindMap = ref(false)
const showInlineSlide = ref(false)
const showInlineVideo = ref(false)
const videoUrl = ref('')
const videoLoading = ref(false)
const slideContent = ref("")

/* ──── Agent / Resource 标签 ──── */

const AGENT_LABELS: Record<string, string> = {
  supervisor: '学习助手',
  profile_agent: '画像采集',
  resource_agent: '资源生成',
  question_agent: '出题',
  path_agent: '路径规划',
  evaluation_agent: '学习评估',
}

function agentLabel(agent?: string): string {
  return AGENT_LABELS[agent || ''] || agent || ''
}

const RESOURCE_TYPE_LABELS: Record<string, string> = {
  document: '知识文档',
  mindmap: '思维导图',
  question_set: '练习题集',
  video_script: '视频脚本',
  code_example: '代码案例',
}

function resourceTypeLabel(type?: string): string {
  return RESOURCE_TYPE_LABELS[type || ''] || '学习资源'
}

const resolvedResourceType = computed(() => {
  if (props.resourceType) return props.resourceType
  if (props.agent === 'resource_agent' && props.content) {
    if (/思维导图|mindmap/i.test(props.content)) return 'mindmap'
    if (/代码|code/i.test(props.content)) return 'code_example'
    if (/题目|习题/i.test(props.content)) return 'question_set'
    if (/视频|video/i.test(props.content)) return 'video_script'
    if (/文档|document/i.test(props.content)) return 'document'
  }
  return undefined
})

/* ── 资源描述（截取前100字符用于 ResourceCard） ── */
const resourceDesc = computed(() => {
  if (!props.content) return undefined
  const cleaned = props.content.replace(/```[\s\S]*?```/g, '').replace(/[#*_>`~|]/g, ' ').replace(/\s+/g, ' ').trim()
  return cleaned.slice(0, 100)
})

const hasHeadings = computed(() => {
  const cleaned = props.content.replace(/```[\s\S]*?```/g, '')
  return /^#{1,3}\s/m.test(cleaned)
})

const resourceIcon = computed<string>(() => {
  const icons: Record<string, string> = {
    document: 'Document',
    mindmap: 'DataBoard',
    question_set: 'List',
    video_script: 'VideoCamera',
    code_example: 'Monitor',
  }
  return icons[resolvedResourceType.value || ''] || 'Document'
})

const contentPreviewText = computed(() => {
  const t = props.content?.trim() || ''
  if (!t) return '正在生成...'
  return t.length > 80 ? t.slice(0, 80) + '...' : t
})

const showMindMapBtn = computed(() => {
  return props.agent === 'resource_agent' && hasHeadings.value && props.content.length > 0 && !props.isStreaming
})

const mindMapContent = computed(() => props.content.replace(/```[\s\S]*?```/g, ''))

function toggleMindMap() {
  showMindMap.value = !showMindMap.value
}

/* ──── 图片灯箱 ──── */
const lightboxImage = ref<string | null>(null)

function openLightbox(src: string) {
  lightboxImage.value = src
}

function closeLightbox() {
  lightboxImage.value = null
}

/* ──── 仅文档和视频脚本资源支持视频讲解 ──── */
const isSlideshowType = computed(() => {
  const t = resolvedResourceType.value
  return t === 'document' || t === 'video_script'
})

function goToSlideshow() {
  if (props.resourceId) {
    router.push(`/resources/${props.resourceId}?mode=slideshow`)
  }
}

/* ══════════════════════════════════════════════
   内容段解析 — 分离文本和代码块
   ══════════════════════════════════════════════ */

interface ContentSegment {
  type: 'text' | 'code'
  content: string
  language?: string
}

const textContent = computed(() => (props.content || '').trim())

const contentSegments = computed<ContentSegment[]>(() => {
  const raw = props.content || ''
  if (!raw.trim()) return []

  const segments: ContentSegment[] = []
  const regex = /```(\w*)\n([\s\S]*?)```/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = regex.exec(raw)) !== null) {
    const lang = match[1] || ''
    // mermaid 块保留在文本段中，由 Mermaid 渲染器处理
    if (lang === 'mermaid') continue

    // 文本段（代码块之前的内容）
    if (match.index > lastIndex) {
      const txt = raw.slice(lastIndex, match.index).trim()
      if (txt) {
        segments.push({ type: 'text', content: txt })
      }
    }
    // 代码段
    segments.push({
      type: 'code',
      content: match[2].trimEnd(),
      language: lang || undefined,
    })
    lastIndex = match.index + match[0].length
  }

  // 最后一段文本
  if (lastIndex < raw.length) {
    const txt = raw.slice(lastIndex).trim()
    if (txt) {
      segments.push({ type: 'text', content: txt })
    }
  }

  // 全部是文本（无代码块）
  if (segments.length === 0 && raw.trim()) {
    segments.push({ type: 'text', content: raw.trim() })
  }

  return segments
})

/* ── 文本段的 Markdown 渲染器 ── */

const renderer = new Renderer()
renderer.code = function (token: { text: string; lang?: string; escaped?: boolean }): string {
  const lang = token.lang || 'text'
  const escapedToken = token.escaped !== false
  let rawCode = token.text

  if (escapedToken) {
    rawCode = rawCode
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
  }

  const highlighted = highlightCode(rawCode, lang)
  const encoded = safeBtoa(rawCode)

  return (
    `<div class="cb">` +
    `<div class="cb-hdr"><span class="cb-lang">${lang}</span><button class="cb-copy" data-code="${encoded}">${SVG_COPY} <span>复制</span></button></div>` +
    `<pre class="cb-pre"><code class="language-${lang}">${highlighted}</code></pre>` +
    `</div>`
  )
}

const textMarked = new Marked()
textMarked.use({ renderer })

function renderMarkdown(md: string): string {
  try {
    let content = md
    // mermaid 预处理
    content = content.replace(/```mermaid\n([\s\S]*?)```/g, (_: string, code: string) => {
      return '<pre class="mermaid">' + code.trim() + '</pre>'
    })
    const raw = textMarked.parse(content) as string
    return DOMPurify.sanitize(raw, {
      ALLOWED_ATTR: ['class', 'href', 'target', 'data-code', 'viewBox', 'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'd', 'width', 'height', 'rx', 'ry', 'cx', 'cy', 'r', 'x1', 'y1', 'x2', 'y2', 'points', 'transform', 'opacity', 'style', 'xmlns', 'text-anchor', 'dominant-baseline', 'font-size', 'font-family', 'font-weight', 'marker-end', 'alt', 'src'],
      ALLOWED_TAGS: ['a', 'b', 'i', 'em', 'strong', 'p', 'br', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'code', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'img', 'span', 'div', 'button', 'svg', 'path', 'rect', 'line', 'circle', 'ellipse', 'text', 'tspan', 'polyline', 'polygon', 'g', 'marker', 'linearGradient', 'stop', 'defs', 'filter', 'feDropShadow'],
      ADD_ATTR: ['target'],
    })
  } catch {
    return md
  }
}

/* ── 流式模式的 rendered（保持原有行为） ── */

const rendered = computed(() => {
  if (!props.content && props.isStreaming) {
    return '<div class="streaming-loader"><span></span><span></span><span></span></div>'
  }
  if (props.isStreaming && props.content) {
    const cleaned = (props.content || '')
      .replace(/<span\b[^>]*>/gi, '')
      .replace(/<\/span>/gi, '')
      .replace(/<div\b[^>]*>/gi, '')
      .replace(/<\/div>/gi, '')
      .replace(/&lt;span\b[^&]*&gt;/gi, '')
      .replace(/&lt;\/span&gt;/gi, '')
      .replace(/"(?:sk|ss|sc|sn|sf|sd|hl|k|n|s|f|d|c|o|p|w|kc|kp)">/gi, '')
      .replace(/\s*class\s*=\s*"(?:sk|ss|sc|sn|sf|sd)[^"]*"/gi, '')
    return '<p>' + cleaned.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>') + '</p>'
  }
  // 非流式模式由 segment 渲染接管
  return ''
})

/* ──── Mermaid 图渲染 ──── */

async function renderMermaidDiagrams() {
  await import('vue').then(m => m.nextTick())
  const el = bodyRef.value
  if (!el) return
  let mermaidEls = el.querySelectorAll<HTMLElement>('.mermaid:not(.mermaid-rendered)')
  if (mermaidEls.length === 0) {
    const codeBlocks = el.querySelectorAll<HTMLElement>('.language-mermaid')
    codeBlocks.forEach(cb => { cb.classList.add('mermaid') })
    mermaidEls = el.querySelectorAll<HTMLElement>('.mermaid:not(.mermaid-rendered)')
  }
  for (const me of Array.from(mermaidEls)) {
    try {
      const code = me.textContent || ''
      if (!code.trim()) continue
      const id = 'mermaid-' + Math.random().toString(36).slice(2, 8)
      const { svg } = await mermaid.render(id, code)
      me.innerHTML = DOMPurify.sanitize(svg, {
        USE_PROFILES: { svg: true, svgFilters: true },
        ADD_ATTR: ['viewBox', 'fill', 'stroke', 'stroke-width', 'd', 'width', 'height'],
      })
      me.classList.add('mermaid-rendered')
    } catch (_) { me.classList.add('mermaid-error') }
  }
}
watch(() => props.isStreaming, (s) => { if (!s) setTimeout(renderMermaidDiagrams, 100) })
watch(() => props.content, () => { if (!props.isStreaming) setTimeout(renderMermaidDiagrams, 100) })
onMounted(() => { if (!props.isStreaming && props.content) setTimeout(renderMermaidDiagrams, 200) })

/* ──── TTS 朗读 ──── */

const ttsLoading = ref(false)
const ttsPlaying = ref(false)
let ttsAudio: HTMLAudioElement | null = null
let ttsBlobUrl: string | null = null

const plainText = computed(() =>
  (props.content || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#*_>`~|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim(),
)

function stopTts() {
  if (ttsAudio) {
    ttsAudio.pause()
    ttsAudio.currentTime = 0
  }
  function goToSlideshow() {
    if (props.resourceId) {
      showInlineSlide.value = true
      getResource(props.resourceId).then(function(r) {
        slideContent.value = r.content || ''
      }).catch(function() {
        ElMessage.error('加载资源失败')
        showInlineSlide.value = false
      })
    }
  }

  ttsPlaying.value = false
}

function openVideoResource() {
    goToSlideshow()
  }
async function openInlineVideo() {
  if (videoUrl.value) {
    showInlineVideo.value = true
    return
  }
  videoLoading.value = true
  try {
    const resp = await api.post('/video/generate', {
      script_text: props.content || '',
      title: props.resourceTitle || '视频讲解'
    })
    if (resp.data?.url) {
      videoUrl.value = resp.data.url
      showInlineVideo.value = true
    } else {
      goToSlideshow()
    }
  } catch {
    goToSlideshow()
  } finally {
    videoLoading.value = false
  }
}



  async function toggleSpeak() {
  if (ttsPlaying.value) { stopTts(); return }
  if (!plainText.value) return
  ttsLoading.value = true
  try {
    const url = await synthesizeSpeech(plainText.value)
    if (ttsBlobUrl) URL.revokeObjectURL(ttsBlobUrl)
    ttsBlobUrl = url
    ttsAudio = new Audio(url)
    ttsAudio.onended = () => { ttsPlaying.value = false }
    ttsAudio.onerror = () => { ttsPlaying.value = false }
    await ttsAudio.play()
    ttsPlaying.value = true
  } catch (e) {
    ElMessage.warning('语音合成暂不可用')
  } finally {
    ttsLoading.value = false
  }
}

onUnmounted(() => {
  stopTts()
  if (ttsBlobUrl) URL.revokeObjectURL(ttsBlobUrl)
})

/* ──── 气泡点击委托（处理遗留 .cb-copy 复制按钮）──── */

function onBubbleClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  const btn = target.closest('.cb-copy') as HTMLElement | null
  if (!btn) return
  e.preventDefault()
  e.stopPropagation()

  const encoded = btn.getAttribute('data-code')
  if (!encoded) return
  try {
    const code = safeAtob(encoded)
    navigator.clipboard.writeText(code).then(() => {
      btn.classList.add('copied')
      btn.innerHTML = `${SVG_CHECK} <span>已复制</span>`
      setTimeout(() => {
        btn.classList.remove('copied')
        btn.innerHTML = `${SVG_COPY} <span>复制</span>`
      }, 2000)
    }).catch(() => {
      const ta = document.createElement('textarea')
      ta.value = code
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      btn.classList.add('copied')
      btn.innerHTML = `${SVG_CHECK} <span>已复制</span>`
      setTimeout(() => {
        btn.classList.remove('copied')
        btn.innerHTML = `${SVG_COPY} <span>复制</span>`
      }, 2000)
    })
  } catch {
    // ignore
  }
}
</script>

<style scoped>
/* ═══════════ Layout — Animated Entry ═══════════ */
.msg {
  display: flex;
  gap: 10px;
  padding: 8px 20px;
  max-width: 82%;
  animation: fadeUp 0.4s var(--ease-emphasis) both;
}
.msg.user {
  flex-direction: row-reverse;
  align-self: flex-end;
  margin-left: auto;
  animation-name: fadeDown;
}
.msg.assistant {
  align-self: flex-start;
}

/* ═══════════ Avatar — Subtle glow ═══════════ */
.av {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
  transition: transform var(--transition-normal) var(--ease-bounce);
}
.msg:hover .av { transform: scale(1.05); }
.av.assistant {
  background: #EFF6FF;
  color: var(--primary);
}
.av.user {
  background: var(--primary-light);
  color: var(--primary-dark);
}

/* ═══════════ Bubble — Enhanced depth & shadow ═══════════ */
.bb {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 12px 16px;
  line-height: 1.7;
  max-width: 100%;
  position: relative;
  transition: all var(--transition-normal) var(--ease-standard);
  box-shadow: var(--shadow-xs);
  color: var(--text-primary);
}
.bb:hover {
  box-shadow: var(--shadow-sm);
  border-color: var(--border);
}
.user .bb {
  background: var(--primary-light);
  color: var(--primary-dark);
  border-color: rgba(37,99,235,.15);
}
.user .bb:hover {
  box-shadow: var(--shadow-sm);
}

/* ═══════════ Cursor — 紧跟文字内联 ═══════════ */
.cursor {
  display: inline;
  color: var(--primary);
  margin-left: 1px;
  animation: blink 0.8s step-end infinite;
  font-weight: 400;
}
.user .cursor { color: rgba(255,255,255,.8); }

/* ═══════════ Empty placeholder ═══════════ */
.empty-placeholder {
  padding: 8px 0;
  color: var(--text-muted);
  font-size: 13px;
  font-style: italic;
}

/* ═══════════ Text segment ═══════════ */
.text-segment {
  color: var(--text-primary);
}

/* ═══════════ Streaming Loader — 三点跳动加载态 ═══════════ */
.body :deep(.streaming-loader) {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 0;
}
.body :deep(.streaming-loader span) {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #93C5FD;
  animation: loaderBounce 1.2s ease-in-out infinite;
}
.body :deep(.streaming-loader span:nth-child(2)) { animation-delay: 0.15s; background: #60A5FA; }
.body :deep(.streaming-loader span:nth-child(3)) { animation-delay: 0.3s; background: #3B82F6; }
@keyframes loaderBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* ═══════════ Agent switch tag ═══════════ */
.tag {
  font-size: 11px;
  color: var(--primary);
  margin-bottom: 6px;
  padding: 3px 10px;
  background: #EFF6FF;
  border-radius: 999px;
  display: inline-block;
  font-weight: 600;
  border: 1px solid rgba(37,99,235,.1);
}

/* ═══════════ Agent header ═══════════ */
.ah {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.ah-name {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}
.user .ah-name { color: rgba(255,255,255,.8); }
.ah-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  line-height: 18px;
  white-space: nowrap;
  border: 1px solid;
  transition: all var(--transition-fast);
}
.ah-badge:hover { transform: scale(1.05); }
.ah-badge.document { background: rgba(37,99,235,.12); color: var(--primary); border-color: rgba(37,99,235,.2); }
.ah-badge.mindmap { background: rgba(16,185,129,.12); color: #10B981; border-color: rgba(16,185,129,.2); }
.ah-badge.code_example { background: rgba(139,92,246,.12); color: #8B5CF6; border-color: rgba(139,92,246,.2); }
.ah-badge.question_set { background: rgba(245,158,11,.12); color: #F59E0B; border-color: rgba(245,158,11,.2); }
.ah-badge.video_script { background: rgba(59,130,246,.12); color: #3B82F6; border-color: rgba(59,130,246,.2); }
.user .ah-badge { background: rgba(255,255,255,.2); color: #fff; border-color: rgba(255,255,255,.25); }

/* ═══════════ Body / Markdown — 强制深色文字 ═══════════ */
.body {
  color: var(--text-primary) !important;
  font-size: 14px;
  line-height: 1.75;
}

/* ── 多模态：用户消息中的图片 ── */
.msg-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.msg-img {
  border-radius: 10px;
  cursor: pointer;
  object-fit: cover;
  border: 1px solid rgba(0,0,0,.08);
  transition: transform 0.2s var(--ease-bounce), box-shadow 0.2s var(--ease-standard);
}

/* ── 方案A: CSS 增强 image-card ── */
.image-card {
  max-width: 320px;
  max-height: 300px;
  box-shadow: 0 2px 8px rgba(0,0,0,.06);
}
.image-card:hover {
  transform: scale(1.04);
  box-shadow: 0 6px 20px rgba(0,0,0,.14);
}

.body :deep(p) {
  margin: 0 0 6px;
  color: var(--text-secondary);
  font-size: 14px;
}
.body :deep(p:last-child) { margin-bottom: 0; }
.body :deep(ul), .body :deep(ol) {
  padding-left: 20px;
  margin-bottom: 6px;
  color: var(--text-secondary);
}
.body :deep(li) {
  margin-bottom: 2px;
  color: var(--text-secondary);
  font-size: 14px;
}
.body :deep(h1), .body :deep(h2), .body :deep(h3) { margin: 10px 0 4px; line-height: 1.35; color: var(--text-primary); }
.body :deep(h1) { font-size: 18px; }
.body :deep(h2) { font-size: 16px; }
.body :deep(h3) { font-size: 14px; }
.body :deep(blockquote) {
  border-left: 3px solid var(--primary);
  margin: 6px 0;
  padding: 4px 12px;
  color: var(--text-secondary);
  background: var(--bg-input);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
}
.body :deep(a) { color: var(--primary); text-decoration: underline; }
.body :deep(table) { border-collapse: collapse; margin: 6px 0; width: 100%; }
.body :deep(th), .body :deep(td) { border: 1px solid var(--border); padding: 6px 10px; text-align: left; font-size: 13px; }
.body :deep(th) { background: var(--bg-input); font-weight: 600; color: var(--text-secondary); }
.body :deep(code:not(.cb-pre code):not(.cc-code)) {
  background: var(--bg-input);
  color: var(--text-primary);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-family: 'Menlo', 'Consolas', 'Courier New', monospace;
}
.user .body :deep(code:not(.cb-pre code):not(.cc-code)) {
  background: rgba(255,255,255,0.2);
  color: #fff;
}

/* ═══════════ Legacy Code Block (.cb) — 降级渲染 ═══════════ */
:deep(.cb) {
  margin: 10px 0;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: #1E293B;
  border: 1px solid #334155;
}
:deep(.cb-hdr) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: rgba(15,23,42,.8);
  border-bottom: 1px solid #1E293B;
}
:deep(.cb-lang) {
  font-size: 11px;
  font-weight: 600;
  color: #64748B;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
:deep(.cb-copy) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border: 1px solid #334155;
  border-radius: var(--radius-sm);
  background: #1E293B;
  color: #94A3B8;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}
:deep(.cb-copy:hover) {
  background: #334155;
  border-color: #475569;
  color: #E2E8F0;
}
:deep(.cb-copy.copied) {
  background: rgba(16,185,129,.15);
  border-color: rgba(16,185,129,.3);
  color: #34D399;
}
:deep(.cb-pre) {
  margin: 0;
  padding: 12px 16px;
  overflow-x: auto;
  font-size: var(--font-sm);
  line-height: 1.65;
  color: #E2E8F0;
}
:deep(.cb-pre code) {
  display: block;
  background: none;
  padding: 0;
  font-family: 'Menlo', 'Consolas', 'Courier New', monospace;
  tab-size: 4;
  white-space: pre;
}

/* Syntax highlight colors (legacy + shared) */
:deep(.sk) { color: #C084FC; font-weight: 500; }
:deep(.ss) { color: #6EE7B7; }
:deep(.sc) { color: #64748B; font-style: italic; }
:deep(.sn) { color: #FBBF24; }
:deep(.sf) { color: #7DD3FC; }
:deep(.sd) { color: #FDA4AF; }

/* ═══════════ MindMap ═══════════ */
.mindmap-section {
  margin-top: 12px;
  border-top: 1px solid var(--border);
  padding-top: 10px;
}
.inline-mindmap-wrap { margin-top: 8px; }
.user .mindmap-section { border-color: rgba(255,255,255,0.15); }

/* ═══════════ 朗读按钮 (TTS) ═══════════ */

/* 视频触发器按钮行 */


/* 内容生成预览卡片 */
.res-preview {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; margin: 6px 0;
  background: var(--bg-page); border: 1px dashed var(--border);
  border-radius: var(--radius-md);
  animation: fade-in 0.3s ease;
}
.res-preview .res-spin { color: var(--primary); animation: spin 1s linear infinite; }
.res-preview-info { flex: 1; min-width: 0; }
.res-preview-type { font-size: 11px; color: var(--text-muted); }
.res-preview-title { font-size: 12px; color: var(--text-primary); font-weight: 500; }
/* 内嵌播放器容器 */
.inline-player-wrap { margin: 8px 0; border-radius: var(--radius-lg); overflow: hidden; }
.inline-player-loading {
  display: flex; align-items: center; gap: 10px; padding: 24px;
  justify-content: center; color: var(--text-muted); font-size: 13px;
}

.video-trigger-row {
  margin-top: 8px;
}
.video-trigger-btn {
  width: 100%;
}

.speak-row { margin-top: 8px; }
.speak-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.speak-btn:hover:not(:disabled) { color: var(--primary); border-color: var(--primary); }
.speak-btn:disabled { opacity: 0.6; cursor: default; }

/* ═══════════ 图片灯箱 (Lightbox) ═══════════ */
.lightbox-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  background: rgba(0, 0, 0, 0.82);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.25s var(--ease-standard) both;
}
.lightbox-close {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
  z-index: 10001;
}
.lightbox-close:hover {
  background: rgba(255, 255, 255, 0.22);
  transform: scale(1.08);
}
.lightbox-img {
  max-width: 90vw;
  max-height: 90dvh;
  object-fit: contain;
  border-radius: var(--radius-lg);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
  animation: scaleIn 0.3s var(--ease-emphasis) both;
}

.collab-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  font-weight: 600;
  color: #8B5CF6;
  background: rgba(139,92,246,.08);
  padding: 1px 7px;
  border-radius: 8px;
  margin-left: 6px;
}
</style>
