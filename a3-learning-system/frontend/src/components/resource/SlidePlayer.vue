<!--
SlidePlayer — 视频讲解幻灯片组件（方案A: TTS + Mermaid 轮播）

功能：
  1. 按 ### / ## 标题拆分内容为幻灯片
  2. 每张幻灯片显示：标题 + 正文（Markdown渲染）+ Mermaid 图表
  3. TTS 语音朗读每张幻灯片，朗读完毕后自动翻页
  4. 若 TTS 不可用，回退到 3 秒定时器自动翻页
  5. 底部控制栏：上一页/播放暂停/下一页 + 进度圆点
  6. 加载态（合成语音中…）、错误回退、空内容兜底

Props:
  content   — Markdown 资源正文
  visible   — 是否显示（支持 v-model:visible）
  autoPlay  — 是否打开后自动播放

样式：深色剧场模式，白色文字，CSS fade 过渡
-->
<template>
  <Transition name="theater-zoom">
    <div v-if="visible" class="slide-theater">
      <!-- 关闭按钮 -->
      <button class="theater-close" @click="close" title="关闭">
        <el-icon :size="20"><Close /></el-icon>
      </button>

      <!-- 空状态 -->
      <div v-if="slides.length === 0" class="theater-empty">
        <svg viewBox="0 0 160 100" class="empty-svg">
          <rect x="20" y="15" width="120" height="70" rx="10" fill="none" stroke="rgba(148,163,184,.3)" stroke-width="2" />
          <line x1="45" y1="38" x2="115" y2="38" stroke="rgba(148,163,184,.25)" stroke-width="2" />
          <line x1="45" y1="52" x2="100" y2="52" stroke="rgba(148,163,184,.2)" stroke-width="2" />
          <line x1="45" y1="66" x2="85" y2="66" stroke="rgba(148,163,184,.15)" stroke-width="2" />
        </svg>
        <p>无可拆分的幻灯片内容</p>
        <span class="empty-hint">内容需包含 ## 或 ### 标题以自动拆分为幻灯片</span>
      </div>

      <!-- 幻灯片舞台 -->
      <div v-else class="theater-stage">
        <Transition :name="transitionName" mode="out-in">
          <div :key="currentIndex" class="slide-panel">
            <!-- 幻灯片标题 -->
            <h2 v-if="currentSlide.heading" class="slide-heading">{{ currentSlide.heading }}</h2>

            <!-- 正文（Markdown 渲染） -->
            <div v-if="currentSlide.body" class="slide-body" v-html="renderedSlideBody" />

            <!-- Mermaid 图表 -->
            <div v-if="currentSlide.mermaidCode" class="slide-mermaid-wrap">
              <div v-if="mermaidLoading" class="mermaid-loading">
                <el-icon class="spin"><Loading /></el-icon>
                <span>渲染图表…</span>
              </div>
              <div v-else-if="mermaidSvg" class="mermaid-svg" v-html="mermaidSvg" />
              <div v-else class="mermaid-error">图表渲染失败</div>
            </div>

            <!-- 无内容兜底 -->
            <p v-if="!currentSlide.heading && !currentSlide.body && !currentSlide.mermaidCode" class="slide-empty">
              此幻灯片无内容
            </p>
          </div>
        </Transition>
      </div>

      <!-- 控制栏 -->
      <div v-if="slides.length > 0" class="theater-controls">
        <!-- 左侧：导航按钮 -->
        <div class="controls-left">
          <button class="ctrl-btn" :disabled="!hasPrev" @click="prev" title="上一页">
            <el-icon :size="16"><ArrowLeft /></el-icon>
          </button>
          <button
            class="ctrl-btn play-btn"
            :class="{ loading: isTtsLoading }"
            :disabled="isTtsLoading"
            @click="togglePlay"
            :title="isPlaying ? '暂停' : '播放'"
          >
            <el-icon v-if="isTtsLoading" class="spin" :size="16"><Loading /></el-icon>
            <el-icon v-else :size="16"><component :is="isPlaying ? 'VideoPause' : 'VideoPlay'" /></el-icon>
          </button>
          <button class="ctrl-btn" :disabled="!hasNext" @click="next" title="下一页">
            <el-icon :size="16"><ArrowRight /></el-icon>
          </button>
          <span class="slide-counter">{{ currentIndex + 1 }} / {{ slides.length }}</span>
          <span v-if="ttsUnavailable" class="tts-badge">无语音</span>
        </div>

        <!-- 中间：进度圆点 -->
        <div class="controls-center">
          <button
            v-for="(_, i) in slides"
            :key="i"
            class="progress-dot"
            :class="{ active: i === currentIndex, past: i < currentIndex }"
            @click="goToSlide(i)"
            :title="`第 ${i + 1} 页`"
          />
        </div>

        <!-- 右侧：自动翻页速度 -->
        <div class="controls-right">
          <span class="speed-label">间隔 {{ advanceDelaySeconds }}s</span>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import mermaid from 'mermaid'
import { ArrowLeft, ArrowRight, VideoPlay, VideoPause, Close, Loading } from '@element-plus/icons-vue'
import { synthesizeSpeech } from '@/api/tts'

// ── Mermaid 全局初始化（与 ChatMessage.vue 一致） ──
mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  flowchart: { useMaxWidth: true, htmlLabels: true },
  sequence: { useMaxWidth: true },
  gantt: { useMaxWidth: true },
})

// ═══════════════════ Props & Emits ═══════════════════
const props = withDefaults(defineProps<{
  content: string
  visible: boolean
  autoPlay?: boolean
}>(), {
  autoPlay: false,
})

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
}>()

// ═══════════════════ 幻灯片数据结构 ═══════════════════
interface Slide {
  heading: string
  body: string
  mermaidCode: string | null
}

// ═══════════════════ 状态 ═══════════════════
const currentIndex = ref(0)
const isPlaying = ref(false)
const isTtsLoading = ref(false)
const ttsUnavailable = ref(false)
const mermaidLoading = ref(false)
const mermaidSvg = ref('')
const transitionName = ref<'slide-left' | 'slide-right' | 'slide-fade'>('slide-fade')
const advanceDelaySeconds = ref(3)

let advanceTimer: ReturnType<typeof setTimeout> | null = null
let ttsAudio: HTMLAudioElement | null = null
let ttsBlobUrl: string | null = null
let mermaidRenderId = 0

// ═══════════════════ 解析幻灯片 ═══════════════════
function extractMermaidCode(text: string): string | null {
  const match = text.match(/```mermaid\n([\s\S]*?)```/)
  return match ? match[1].trim() : null
}

function removeMermaidBlocks(text: string): string {
  return text.replace(/```mermaid\n[\s\S]*?```/g, '')
}

function parseSlides(content: string): Slide[] {
  if (!content?.trim()) return []

  // 找所有 ### 和 ## 标题的位置
  const headingRegex = /^(#{2,3}) (.+)$/gm
  interface HeadingPos { index: number; endIndex: number; level: number; text: string }
  const headings: HeadingPos[] = []
  let match: RegExpExecArray | null
  while ((match = headingRegex.exec(content)) !== null) {
    headings.push({
      index: match.index,
      endIndex: match.index + match[0].length,
      level: match[1].length,
      text: match[2].trim(),
    })
  }

  if (headings.length === 0) {
    // 无标题 → 单张幻灯片
    const mermaidCode = extractMermaidCode(content)
    return [{ heading: '', body: removeMermaidBlocks(content).trim(), mermaidCode }]
  }

  // 优先用 ###（h3），否则用 ##（h2）
  const hasH3 = headings.some(h => h.level === 3)
  const targetLevel = hasH3 ? 3 : 2
  const targetHeadings = headings.filter(h => h.level === targetLevel)

  if (targetHeadings.length === 0) {
    const mermaidCode = extractMermaidCode(content)
    return [{ heading: '', body: removeMermaidBlocks(content).trim(), mermaidCode }]
  }

  const slides: Slide[] = []
  for (let i = 0; i < targetHeadings.length; i++) {
    const curr = targetHeadings[i]
    const next = targetHeadings[i + 1]
    const bodyStart = curr.endIndex + 1 // 跳过标题行后的换行符
    const bodyEnd = next ? next.index : content.length
    const bodyContent = content.slice(bodyStart, bodyEnd)

    // 从 bodyContent 中移除更深层级的标题文本（保留为正文内容）
    const mermaidCode = extractMermaidCode(bodyContent)
    const body = removeMermaidBlocks(bodyContent).trim()

    slides.push({ heading: curr.text, body, mermaidCode })
  }

  return slides
}

const slides = computed(() => parseSlides(props.content))

const currentSlide = computed(() => {
  if (slides.value.length === 0) {
    return { heading: '', body: '', mermaidCode: null as string | null }
  }
  return slides.value[currentIndex.value] || slides.value[0]
})

const hasPrev = computed(() => currentIndex.value > 0)
const hasNext = computed(() => currentIndex.value < slides.value.length - 1)

// ── 幻灯片正文渲染（Markdown → HTML） ──
const renderedSlideBody = computed(() => {
  const body = currentSlide.value.body
  if (!body) return ''
  try {
    // 移除更深层级的标题标记（保留文本）
    const cleaned = body.replace(/^#{1,4}\s/gm, '')
    const html = marked.parse(cleaned) as string
    return DOMPurify.sanitize(html, {
      ALLOWED_ATTR: ['class', 'href', 'target', 'style'],
      ALLOWED_TAGS: ['a', 'b', 'i', 'em', 'strong', 'p', 'br', 'ul', 'ol', 'li', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'code', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'img', 'span', 'div'],
    })
  } catch {
    return body.replace(/</g, '&lt;').replace(/>/g, '&gt;')
  }
})

// ═══════════════════ Mermaid 渲染 ═══════════════════
async function renderMermaid(code: string): Promise<void> {
  mermaidLoading.value = true
  mermaidSvg.value = ''
  try {
    const id = `slideplayer-mermaid-${++mermaidRenderId}`
    const { svg } = await mermaid.render(id, code)
    mermaidSvg.value = DOMPurify.sanitize(svg, {
      USE_PROFILES: { svg: true, svgFilters: true },
      ADD_ATTR: ['viewBox', 'fill', 'stroke', 'stroke-width', 'd', 'width', 'height'],
    })
  } catch {
    mermaidSvg.value = ''
  } finally {
    mermaidLoading.value = false
  }
}

// ═══════════════════ TTS 语音合成与播放 ═══════════════════
function getSlidePlainText(slide: Slide): string {
  let text = ''
  if (slide.heading) text += slide.heading + '。'
  if (slide.body) {
    const stripped = slide.body
      .replace(/```[\s\S]*?```/g, ' ')     // 代码块
      .replace(/#{1,6}\s/g, '')            // 标题标记
      .replace(/(\*\*|__)(.*?)\1/g, '$2')  // 粗体
      .replace(/(\*|_)(.*?)\1/g, '$2')     // 斜体
      .replace(/`([^`]+)`/g, '$1')         // 行内代码
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // 链接
      .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1') // 图片
      .replace(/^[-*+]\s/gm, '')           // 无序列表标记
      .replace(/^\d+\.\s/gm, '')           // 有序列表标记
      .replace(/^>\s/gm, '')               // 引用标记
      .replace(/\|/g, ' ')                 // 表格分隔符
      .replace(/-{2,}/g, ' ')              // 分隔线
      .replace(/\s+/g, ' ')
      .trim()
    if (stripped) text += stripped
  }
  return text.slice(0, 500) // TTS 限制单次 500 字符
}

async function playSlideTTS(slide: Slide): Promise<void> {
  if (ttsUnavailable.value) return

  const text = getSlidePlainText(slide)
  if (!text.trim()) return

  isTtsLoading.value = true
  try {
    const url = await synthesizeSpeech(text)
    if (ttsBlobUrl) URL.revokeObjectURL(ttsBlobUrl)
    ttsBlobUrl = url
    ttsAudio = new Audio(url)

    return new Promise((resolve) => {
      if (!ttsAudio) { resolve(); return }
      ttsAudio.onended = () => {
        isTtsLoading.value = false
        resolve()
      }
      ttsAudio.onerror = () => {
        isTtsLoading.value = false
        ttsUnavailable.value = true
        resolve()
      }
      ttsAudio.play().catch(() => {
        isTtsLoading.value = false
        ttsUnavailable.value = true
        resolve()
      })
    })
  } catch {
    isTtsLoading.value = false
    ttsUnavailable.value = true
  }
}

function stopTts() {
  if (ttsAudio) {
    ttsAudio.pause()
    ttsAudio.currentTime = 0
    ttsAudio = null
  }
  isTtsLoading.value = false
}

// ═══════════════════ 导航与播放控制 ═══════════════════
function clearAdvanceTimer() {
  if (advanceTimer) {
    clearTimeout(advanceTimer)
    advanceTimer = null
  }
}

function goToSlide(index: number, direction?: 'prev' | 'next') {
  if (index < 0 || index >= slides.value.length) return
  stopTts()
  clearAdvanceTimer()

  // 设置过渡方向
  if (direction === 'prev') transitionName.value = 'slide-right'
  else if (direction === 'next') transitionName.value = 'slide-left'
  else transitionName.value = 'slide-fade'

  currentIndex.value = index
}

function next() {
  if (hasNext.value) goToSlide(currentIndex.value + 1, 'next')
  else {
    // 到达最后一页，停止播放
    isPlaying.value = false
  }
}

function prev() {
  if (hasPrev.value) goToSlide(currentIndex.value - 1, 'prev')
}

async function playSlideAndAdvance() {
  if (!isPlaying.value) return
  if (!hasNext.value && currentIndex.value === slides.value.length - 1) {
    // 最后一页播放完毕，停止
    isPlaying.value = false
    return
  }

  const slide = currentSlide.value

  if (!ttsUnavailable.value) {
    // 尝试 TTS
    await playSlideTTS(slide)
  }

  // TTS 结束后或不可用时，等待后再翻页
  if (isPlaying.value) {
    const delay = ttsUnavailable.value ? advanceDelaySeconds.value * 1000 : 500
    advanceTimer = setTimeout(() => {
      advanceTimer = null
      if (isPlaying.value) {
        if (hasNext.value) {
          goToSlide(currentIndex.value + 1, 'next')
          nextTick(() => playSlideAndAdvance())
        } else {
          isPlaying.value = false
        }
      }
    }, delay)
  }
}

function startPlaying() {
  isPlaying.value = true
  nextTick(() => playSlideAndAdvance())
}

function pausePlaying() {
  isPlaying.value = false
  stopTts()
  clearAdvanceTimer()
}

function togglePlay() {
  if (isPlaying.value) {
    pausePlaying()
  } else {
    startPlaying()
  }
}

function close() {
  pausePlaying()
  emit('update:visible', false)
}

// ── 监听 slides 变化（资源内容更新时重置） ──
watch(() => props.content, () => {
  pausePlaying()
  currentIndex.value = 0
  mermaidSvg.value = ''
})

// ── 监听当前幻灯片变化 → 渲染 Mermaid → 自动播放继续 ──
watch(currentIndex, async () => {
  mermaidSvg.value = ''
  if (currentSlide.value.mermaidCode) {
    await renderMermaid(currentSlide.value.mermaidCode)
  }
  // 如果正在播放且 TTS 已加载完成（或不可用），继续流程
  // 由 playSlideAndAdvance 内部处理
})

// ── 可见性变化时自动播放 ──
watch(() => props.visible, (v) => {
  if (v) {
    currentIndex.value = 0
    mermaidSvg.value = ''
    // 渲染首张幻灯片的 Mermaid
    nextTick(async () => {
      if (currentSlide.value.mermaidCode) {
        await renderMermaid(currentSlide.value.mermaidCode)
      }
      if (props.autoPlay) {
        startPlaying()
      }
    })
  } else {
    pausePlaying()
  }
})

// ── 生命周期 ──
onMounted(() => {
  if (props.visible) {
    nextTick(async () => {
      if (currentSlide.value.mermaidCode) {
        await renderMermaid(currentSlide.value.mermaidCode)
      }
      if (props.autoPlay) {
        startPlaying()
      }
    })
  }
})

onUnmounted(() => {
  pausePlaying()
  if (ttsBlobUrl) URL.revokeObjectURL(ttsBlobUrl)
})
</script>

<style scoped>
/* ═══════ 容器 — 深色剧场模式 ═══════ */
.slide-theater {
  position: relative;
  background: #0F172A;
  border: 1px solid #1E293B;
  border-radius: var(--radius-lg);
  padding: 28px 32px 20px;
  margin-top: 20px;
  min-height: 380px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ═══════ Zoom 进出动画 ═══════ */
.theater-zoom-enter-active,
.theater-zoom-leave-active {
  transition: all 0.35s cubic-bezier(.22,.61,.36,1);
}
.theater-zoom-enter-from {
  opacity: 0;
  transform: scale(0.96) translateY(-8px);
}
.theater-zoom-leave-to {
  opacity: 0;
  transform: scale(0.96) translateY(-8px);
}

/* ═══════ 关闭按钮 ═══════ */
.theater-close {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 10;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 50%;
  background: rgba(255,255,255,.06);
  color: #94A3B8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}
.theater-close:hover {
  background: rgba(255,255,255,.12);
  color: #E2E8F0;
}

/* ═══════ 空状态 ═══════ */
.theater-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #64748B;
  gap: 8px;
}
.empty-svg { width: 140px; height: 90px; opacity: 0.4; }
.theater-empty p { font-size: 16px; font-weight: 600; margin: 0; color: #94A3B8; }
.empty-hint { font-size: 12px; color: #475569; }

/* ═══════ 幻灯片舞台 ═══════ */
.theater-stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 240px;
  padding: 12px 0;
}

.slide-panel {
  padding: 16px 8px;
}

/* ── 幻灯片切换过渡 ── */
.slide-fade-enter-active,
.slide-fade-leave-active {
  transition: opacity 0.45s ease;
}
.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
}

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.4s cubic-bezier(.22,.61,.36,1);
}
.slide-left-enter-from {
  opacity: 0;
  transform: translateX(30px);
}
.slide-left-leave-to {
  opacity: 0;
  transform: translateX(-30px);
}

.slide-right-enter-active,
.slide-right-leave-active {
  transition: all 0.4s cubic-bezier(.22,.61,.36,1);
}
.slide-right-enter-from {
  opacity: 0;
  transform: translateX(-30px);
}
.slide-right-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

/* ── 标题 ── */
.slide-heading {
  font-size: 22px;
  font-weight: 700;
  color: #F1F5F9;
  margin: 0 0 16px;
  line-height: 1.35;
  letter-spacing: -0.3px;
}

/* ── 正文 ── */
.slide-body {
  color: #CBD5E1;
  font-size: 15px;
  line-height: 1.8;
}
.slide-body :deep(h3),
.slide-body :deep(h4) {
  color: #E2E8F0;
  margin: 16px 0 8px;
  font-size: 16px;
  font-weight: 600;
}
.slide-body :deep(p) {
  margin: 0 0 10px;
}
.slide-body :deep(ul),
.slide-body :deep(ol) {
  padding-left: 22px;
  margin: 8px 0;
}
.slide-body :deep(li) {
  margin: 3px 0;
  color: #CBD5E1;
}
.slide-body :deep(code) {
  background: rgba(255,255,255,.08);
  color: #E2E8F0;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}
.slide-body :deep(pre) {
  background: #1E293B;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 14px 16px;
  overflow-x: auto;
  margin: 10px 0;
  color: #E2E8F0;
  font-size: 13px;
  line-height: 1.6;
}
.slide-body :deep(pre code) {
  background: none;
  padding: 0;
  font-size: inherit;
}
.slide-body :deep(blockquote) {
  border-left: 3px solid #3B82F6;
  padding: 6px 14px;
  margin: 10px 0;
  background: rgba(59,130,246,.08);
  border-radius: 0 6px 6px 0;
  color: #94A3B8;
}
.slide-body :deep(a) { color: #60A5FA; text-decoration: underline; }
.slide-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
}
.slide-body :deep(th),
.slide-body :deep(td) {
  border: 1px solid #334155;
  padding: 6px 10px;
  text-align: left;
}
.slide-body :deep(th) { background: rgba(255,255,255,.04); color: #94A3B8; font-weight: 600; }
.slide-body :deep(strong) { color: #F1F5F9; font-weight: 600; }
.slide-body :deep(hr) { border: none; border-top: 1px solid #334155; margin: 14px 0; }

/* ── 无内容 ── */
.slide-empty { color: #64748B; font-style: italic; }

/* ═══════ Mermaid 图表 ═══════ */
.slide-mermaid-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: center;
}
.mermaid-loading {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #64748B;
  font-size: 13px;
  padding: 16px;
}
.mermaid-svg {
  background: rgba(255,255,255,.95);
  border-radius: 10px;
  padding: 16px;
  max-width: 100%;
  overflow-x: auto;
}
.mermaid-svg :deep(svg) {
  max-width: 100%;
  height: auto;
}
.mermaid-error {
  color: #F87171;
  font-size: 12px;
}

/* ═══════ 控制栏 ═══════ */
.theater-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid #1E293B;
  margin-top: 8px;
  gap: 12px;
}

.controls-left {
  display: flex;
  align-items: center;
  gap: 6px;
}
.controls-center {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  justify-content: center;
}
.controls-right {
  display: flex;
  align-items: center;
}

/* ── 按钮 ── */
.ctrl-btn {
  width: 34px;
  height: 34px;
  border: 1px solid #334155;
  border-radius: 50%;
  background: rgba(255,255,255,.04);
  color: #94A3B8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}
.ctrl-btn:hover:not(:disabled) {
  background: rgba(255,255,255,.1);
  border-color: #475569;
  color: #E2E8F0;
}
.ctrl-btn:disabled {
  opacity: 0.35;
  cursor: default;
}
.play-btn {
  width: 40px;
  height: 40px;
  background: rgba(59,130,246,.15);
  border-color: rgba(59,130,246,.3);
  color: #60A5FA;
}
.play-btn:hover:not(:disabled) {
  background: rgba(59,130,246,.25);
  border-color: rgba(59,130,246,.45);
  color: #93C5FD;
}
.play-btn.loading {
  border-color: rgba(245,158,11,.3);
  color: #FBBF24;
}

/* ── 计数器 ── */
.slide-counter {
  font-size: 12px;
  color: #64748B;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  margin: 0 4px;
  white-space: nowrap;
}
.tts-badge {
  font-size: 10px;
  color: #F87171;
  background: rgba(248,113,113,.1);
  border: 1px solid rgba(248,113,113,.2);
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
}
.speed-label {
  font-size: 11px;
  color: #475569;
  font-weight: 500;
}

/* ── 进度圆点 ── */
.progress-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  border: none;
  background: #334155;
  cursor: pointer;
  transition: all 0.25s ease;
  padding: 0;
}
.progress-dot:hover {
  background: #64748B;
  transform: scale(1.3);
}
.progress-dot.active {
  background: #3B82F6;
  box-shadow: 0 0 8px rgba(59,130,246,.4);
  transform: scale(1.25);
}
.progress-dot.past {
  background: #475569;
}

/* ── spin 动画 ── */
.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }

/* ── 响应式 ── */
@media (max-width: 640px) {
  .slide-theater {
    padding: 20px 16px 14px;
    min-height: 320px;
  }
  .slide-heading { font-size: 18px; }
  .slide-body { font-size: 14px; }
  .theater-controls { flex-wrap: wrap; justify-content: center; gap: 8px; }
  .controls-center { order: 3; flex-basis: 100%; }
  .slide-counter { font-size: 11px; }
}
</style>
