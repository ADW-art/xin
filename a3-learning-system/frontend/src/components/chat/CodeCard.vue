<!--
  CodeCard -- 增强型代码卡片组件

  功能：
  - 语言自动检测（从代码块标记提取）
  - 语法高亮（14+语言，通过共享 highlight 工具）
  - 行号（CSS 计数器）
  - 折叠/展开（超过20行自动折叠）
  - 一键复制（含"已复制"反馈动画）
  - 深色主题（#1e1e1e 背景）

  Props:
    code     — 原始代码字符串
    language — 可选的语言标识（如 py, js, ts 等），不传则显示 "code"
-->
<template>
  <div class="code-card" :class="{ 'cc-collapsed': isCollapsed }">
    <!-- Header bar -->
    <div class="cc-header">
      <span class="cc-lang">{{ displayLang }}</span>
      <div class="cc-actions">
        <button
          v-if="totalLines > COLLAPSE_THRESHOLD"
          class="cc-btn cc-toggle"
          @click="toggleCollapse"
        >
          <span class="cc-toggle-arrow" :class="{ rotated: !isCollapsed }">&#9660;</span>
          {{ isCollapsed ? `显示全部 (${totalLines} 行)` : '收起' }}
        </button>
        <button class="cc-btn cc-copy-btn" @click="copyCode">
          <span v-html="copied ? SVG_CHECK : SVG_COPY" class="cc-copy-icon" />
          <span>{{ copied ? '已复制' : '复制' }}</span>
        </button>
      </div>
    </div>

    <!-- Code body -->
    <div class="cc-body" ref="bodyRef" :style="{ maxHeight: isCollapsed ? '420px' : 'none' }">
      <pre class="cc-pre"><code class="cc-code" v-html="highlighted" /></pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { highlightCode, SVG_COPY, SVG_CHECK, safeBtoa, safeAtob } from '@/utils/highlight'

const props = defineProps<{
  code: string
  language?: string
}>()

const COLLAPSE_THRESHOLD = 20
const bodyRef = ref<HTMLElement | null>(null)
const isCollapsed = ref(false)
const copied = ref(false)

/* ── 显示语言 ── */
const displayLang = computed(() => {
  if (props.language && props.language !== 'text') return props.language
  // Auto-detect from code content
  const firstLine = props.code.trimStart().split('\n')[0] || ''
  if (/^#!/.test(firstLine)) {
    const m = firstLine.match(/^#!\s*(?:\S*\/)?(\w+)/)
    if (m) return m[1]
  }
  return 'code'
})

/* ── 总行数 ── */
const totalLines = computed(() => {
  // 去除末尾空白行
  return props.code.trimEnd().split('\n').length
})

/* ── 初始折叠判断 ── */
// 在首次渲染时判断是否需要折叠
const initCollapsed = computed(() => totalLines.value > COLLAPSE_THRESHOLD)
// 同步初始折叠状态
if (initCollapsed.value && !isCollapsed.value) {
  // 延迟设置，避免在 setup 阶段就触发
  setTimeout(() => { isCollapsed.value = true }, 0)
}

/* ── 高亮代码 ── */
const highlighted = computed(() => highlightCode(props.code, props.language))

/* ── 折叠/展开 ── */
function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
}

/* ── 复制代码 ── */
async function copyCode() {
  try {
    await navigator.clipboard.writeText(props.code)
  } catch {
    // Fallback: textarea 方案
    const ta = document.createElement('textarea')
    ta.value = props.code
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }
  copied.value = true
  setTimeout(() => {
    copied.value = false
  }, 2000)
}
</script>

<style scoped>
/* ═══════════ Container ═══════════ */
.code-card {
  margin: 10px 0;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: #1e1e1e;
  border: 1px solid #333;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  transition: box-shadow var(--transition-normal) var(--ease-standard);
}
.code-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

/* ═══════════ Header ═══════════ */
.cc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: #252526;
  border-bottom: 1px solid #333;
  user-select: none;
}
.cc-lang {
  font-size: 11px;
  font-weight: 600;
  color: #858585;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  padding: 2px 8px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: var(--radius-sm);
}
.cc-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cc-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid #404040;
  border-radius: var(--radius-sm);
  background: #2d2d2d;
  color: #bbb;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
  font-family: inherit;
  line-height: 1.4;
}
.cc-btn:hover {
  background: #383838;
  border-color: #555;
  color: #e0e0e0;
}
.cc-toggle-arrow {
  font-size: 9px;
  transition: transform 0.2s ease;
}
.cc-toggle-arrow.rotated {
  transform: rotate(180deg);
}
.cc-copy-icon {
  display: inline-flex;
  align-items: center;
}
.cc-copy-btn {
  min-width: 64px;
  justify-content: center;
}
.cc-copy-btn:has(span:only-of-type) {
  /* 回退到只有文字时的样式 */
}

/* ── 复制成功态 ── */
.cc-copy-btn.copied-state {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.25);
  color: #34d399;
}

/* ═══════════ Body ═══════════ */
.cc-body {
  overflow: auto;
  transition: max-height 0.35s var(--ease-emphasis);
}
.cc-collapsed .cc-body {
  position: relative;
}
/* 折叠渐变遮罩 */
.cc-collapsed .cc-body::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 60px;
  background: linear-gradient(to bottom, transparent, #1e1e1e 80%);
  pointer-events: none;
}
.cc-pre {
  margin: 0;
  padding: 14px 0;
  overflow-x: auto;
  font-size: var(--font-sm);
  line-height: 1.65;
  color: #d4d4d4;
  counter-reset: line;
  tab-size: 4;
}
.cc-code {
  display: block;
  background: none;
  padding: 0;
  font-family: 'Menlo', 'Consolas', 'Courier New', monospace;
  tab-size: 4;
  white-space: pre;
}

/* ═══════════ Line numbers (CSS counter) ═══════════ */
/* 用 :deep 让 highlight 输出的 span 享有行号 */
.cc-code :deep(.code-line) {
  display: block;
  counter-increment: line;
}
.cc-code :deep(.code-line)::before {
  content: counter(line);
  display: inline-block;
  width: 44px;
  margin-right: 12px;
  text-align: right;
  color: #555;
  font-size: 11px;
  user-select: none;
  flex-shrink: 0;
}

/* ═══════════ Syntax Colors ═══════════ */
:deep(.sk) {
  color: #c084fc;
  font-weight: 500;
}
:deep(.ss) {
  color: #6ee7b7;
}
:deep(.sc) {
  color: #6a9955;
  font-style: italic;
}
:deep(.sn) {
  color: #fbbf24;
}
:deep(.sf) {
  color: #7dd3fc;
}
:deep(.sd) {
  color: #fda4af;
}
</style>
