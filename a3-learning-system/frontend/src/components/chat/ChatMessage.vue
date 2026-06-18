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
            class="msg-img"
            @click="previewImage(src)"
          />
        </div>
        <div v-html="rendered" />
        <span v-if="isStreaming" class="cursor">|</span>
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

      <!-- Resource preview card -->
      <div v-if="resourceId && resourceTitle" class="res-card">
        <div class="rc-left">
          <div class="rc-icon" :class="resolvedResourceType || 'document'">
            <el-icon :size="22"><component :is="resIcon(resolvedResourceType)" /></el-icon>
          </div>
          <div class="rc-info">
            <span class="rc-type-tag">{{ resourceTypeLabel(resolvedResourceType) }}</span>
            <span class="rc-title">{{ resourceTitle }}</span>
          </div>
        </div>
        <el-button size="small" type="primary" @click="goToResource">查看详情</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Marked, Renderer } from 'marked'
import DOMPurify from 'dompurify'
import mermaid from 'mermaid'
import MindMap from '@/components/resource/MindMap.vue'

// v3: Mermaid 初始化 (参考 Docusaurus/VuePress 集成模式)
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
  images?: string[]       // 多模态：用户消息中的图片 data URL 列表
  agent?: string
  agentSwitch?: { from: string; to: string }
  isStreaming?: boolean
  resourceType?: string
  resourceId?: number
  resourceTitle?: string
}>()

const router = useRouter()
const bodyRef = ref<HTMLElement | null>(null)
const showMindMap = ref(false)

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

function resIcon(type?: string): string {
  const map: Record<string, string> = {
    document: 'Document',
    mindmap: 'DataBoard',
    question_set: 'EditPen',
    video_script: 'VideoPlay',
    code_example: 'Monitor',
  }
  return map[type || ''] || 'Document'
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

const hasHeadings = computed(() => {
  const cleaned = props.content.replace(/```[\s\S]*?```/g, '')
  return /^#{1,3}\s/m.test(cleaned)
})

const showMindMapBtn = computed(() => {
  return props.agent === 'resource_agent' && hasHeadings.value && props.content.length > 0 && !props.isStreaming
})

const mindMapContent = computed(() => props.content.replace(/```[\s\S]*?```/g, ''))

function toggleMindMap() {
  showMindMap.value = !showMindMap.value
}

// 多模态：图片预览（点击放大）
function previewImage(src: string) {
  window.open(src, '_blank')
}

// v3: Mermaid diagram rendering
async function renderMermaidDiagrams() {
  await import('vue').then(m => m.nextTick())
  const el = bodyRef.value
  if (!el) return
  // Find both <pre class="mermaid"> and <code class="language-mermaid"> patterns
  let mermaidEls = el.querySelectorAll<HTMLElement>('.mermaid:not(.mermaid-rendered)')
  if (mermaidEls.length === 0) {
    // Fallback: look for code blocks rendered by marked as language-mermaid
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
      // XSS防护：对Mermaid渲染的SVG进行sanitize
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

function goToResource() {
  if (props.resourceId) {
    router.push(`/resources/${props.resourceId}`)
  }
}

/* ── Syntax highlighting (with LRU cache) ── */
const _hlCache = new Map<string, string>()
const HL_CACHE_MAX = 100 // 最大缓存条目数

function highlightCode(code: string, lang?: string): string {
  // 缓存键：代码前200字符 + 语言（避免大字符串作为key）
  const cacheKey = `${lang || 'text'}:${code.slice(0, 200)}`
  if (_hlCache.has(cacheKey)) return _hlCache.get(cacheKey)!

  let escaped = code
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  if (!lang || lang === 'text' || lang === 'plaintext' || lang === 'plain') return escaped

  if (lang === 'python' || lang === 'py') {
    const kw = 'False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield'
    escaped = escaped.replace(new RegExp(`\\b(${kw})\\b`, 'g'), '<span class="sk">$1</span>')
    escaped = escaped.replace(/(@\w+)/g, '<span class="sd">$1</span>')
    escaped = escaped.replace(/\b([a-zA-Z_]\w*)(\s*\()/g, '<span class="sf">$1</span>$2')
    escaped = escaped.replace(/(#.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/("""[\s\S]*?""")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/('''[\s\S]*?''')/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/('(?:[^'\\]|\\.)*')/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'javascript' || lang === 'js' || lang === 'typescript' || lang === 'ts') {
    const kw = 'break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|finally|for|function|if|import|in|instanceof|let|new|return|super|switch|this|throw|try|typeof|var|void|while|with|yield|async|await|from|of|static|enum|interface|type|implements'
    escaped = escaped.replace(new RegExp(`\\b(${kw})\\b`, 'g'), '<span class="sk">$1</span>')
    escaped = escaped.replace(/(\/\/.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/('(?:[^'\\]|\\.)*')/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/(`(?:[^`\\]|\\.)*`)/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'bash' || lang === 'sh' || lang === 'shell') {
    escaped = escaped.replace(/(#.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/('(?:[^'\\]|\\.)*')/g, '<span class="ss">$1</span>')
    const cmds = 'echo|cd|ls|cp|mv|rm|mkdir|git|npm|pip|python|node|docker|curl|wget|export|source|chmod|cat|grep|find|sed|awk|tar|ssh|scp|sudo|apt|brew|yarn|pnpm|npx|uvicorn|docker-compose|ps|kill'
    escaped = escaped.replace(new RegExp(`\\b(${cmds})\\b`, 'g'), '<span class="sk">$1</span>')
  } else if (lang === 'sql') {
    const kw = 'SELECT|FROM|WHERE|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|ALTER|DROP|INDEX|JOIN|INNER|LEFT|RIGHT|OUTER|ON|AS|AND|OR|NOT|NULL|IS|LIKE|BETWEEN|IN|ORDER|BY|GROUP|HAVING|LIMIT|OFFSET|COUNT|SUM|AVG|MAX|MIN|DISTINCT|PRIMARY|KEY|FOREIGN|REFERENCES|INT|VARCHAR|TEXT|BOOLEAN|DATETIME|JSON'
    escaped = escaped.replace(new RegExp(`\\b(${kw})\\b`, 'gi'), '<span class="sk">$1</span>')
    escaped = escaped.replace(/('(?:[^'\\]|\\.)*')/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'json') {
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")(\s*:)/g, '<span class="sk">$1</span>$2')
    escaped = escaped.replace(/:\s*("(?:[^"\\]|\\.)*")/g, ': <span class="ss">$1</span>')
    escaped = escaped.replace(/\b(true|false|null)\b/g, '<span class="sk">$1</span>')
    escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'html' || lang === 'xml' || lang === 'svg') {
    escaped = escaped.replace(/(&lt;\/?)([\w-]+)/g, '$1<span class="sk">$2</span>')
    escaped = escaped.replace(/\s([\w-]+)(=)/g, ' <span class="sf">$1</span>$2')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/(&lt;!--[\s\S]*?--&gt;)/g, '<span class="sc">$1</span>')
  } else if (lang === 'css' || lang === 'scss') {
    escaped = escaped.replace(/(\/\*[\s\S]*?\*\/)/g, '<span class="sc">$1</span>')
    escaped = escaped.replace(/([.#@][\w-]+)/g, '<span class="sk">$1</span>')
    escaped = escaped.replace(/:([\w-]+)/g, ':<span class="sf">$1</span>')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
    escaped = escaped.replace(/\b(\d+\.?\d*(?:px|em|rem|%|vh|vw|s|ms)?)\b/g, '<span class="sn">$1</span>')
  } else if (lang === 'yaml' || lang === 'yml') {
    escaped = escaped.replace(/(#.*)$/gm, '<span class="sc">$1</span>')
    escaped = escaped.replace(/^(\s*)([\w-]+)(:)/gm, '$1<span class="sk">$2</span>$3')
    escaped = escaped.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ss">$1</span>')
  }

  // 写入缓存，LRU淘汰
  if (_hlCache.size >= HL_CACHE_MAX) {
    const firstKey = _hlCache.keys().next().value
    if (firstKey) _hlCache.delete(firstKey)
  }
  _hlCache.set(cacheKey, escaped)

  return escaped
}

const SVG_COPY = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
const SVG_CHECK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'

function safeBtoa(str: string): string {
  const bytes = new TextEncoder().encode(str)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

function safeAtob(encoded: string): string {
  const binary = atob(encoded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return new TextDecoder().decode(bytes)
}

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

// Use a local marked instance to avoid mutating the global default
const localMarked = new Marked()
localMarked.use({ renderer })

const rendered = computed(() => {
  // 流式输出中且内容为空 → 显示优雅加载态，而非"..."
  if (!props.content && props.isStreaming) {
    return '<div class="streaming-loader"><span></span><span></span><span></span></div>'
  }
  // 流式输出中：跳过marked解析（每chunk都parse严重卡顿），直接HTML转义逐字渲染
  if (props.isStreaming && props.content) {
    return '<p>' + (props.content || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>') + '</p>'
  }
  try {
    // v3: mermaid 预处理
    let mdContent = props.content || ''
    mdContent = mdContent.replace(/```mermaid\n([\s\S]*?)```/g, (_: string, code: string) => {
      return '<pre class="mermaid">' + code.trim() + '</pre>'
    })
    const raw = localMarked.parse(mdContent) as string
    // XSS 防护：过滤不安全的 HTML 标签和属性
    return DOMPurify.sanitize(raw, {
      ALLOWED_ATTR: ['class', 'href', 'target', 'data-code', 'viewBox', 'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'd', 'width', 'height', 'rx', 'ry', 'cx', 'cy', 'r', 'x1', 'y1', 'x2', 'y2', 'points', 'transform', 'opacity', 'style', 'xmlns', 'text-anchor', 'dominant-baseline', 'font-size', 'font-family', 'font-weight', 'marker-end'],
      ALLOWED_TAGS: ['a', 'b', 'i', 'em', 'strong', 'p', 'br', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'code', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'img', 'span', 'div', 'button', 'svg', 'path', 'rect', 'line', 'circle', 'ellipse', 'text', 'tspan', 'polyline', 'polygon', 'g', 'marker', 'linearGradient', 'stop', 'defs', 'filter', 'feDropShadow'],
      ADD_ATTR: ['target'],
    })
  } catch {
    return props.content || ''
  }
})

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
  gap: 6px;
  margin-bottom: 8px;
}
.msg-img {
  max-width: 240px;
  max-height: 200px;
  border-radius: 8px;
  cursor: pointer;
  object-fit: contain;
  border: 1px solid rgba(0,0,0,.08);
  transition: transform 0.15s, box-shadow 0.15s;
}
.msg-img:hover {
  transform: scale(1.03);
  box-shadow: 0 4px 12px rgba(0,0,0,.12);
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
.body :deep(code:not(.cb-pre code)) {
  background: var(--bg-input);
  color: var(--text-primary);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-family: 'Menlo', 'Consolas', 'Courier New', monospace;
}
.user .body :deep(code:not(.cb-pre code)) {
  background: rgba(255,255,255,0.2);
  color: #fff;
}

/* ═══════════ Code Block ═══════════ */
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

/* ═══════════ Resource Card ═══════════ */
.res-card {
  margin-top: 12px;
  border-top: 1px solid var(--border);
  padding-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.user .res-card { border-color: rgba(255,255,255,0.15); }
.rc-left { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }
.rc-icon {
  width: 38px; height: 38px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid;
}
.rc-icon.document { background: rgba(59,130,246,.1); color: var(--primary); border-color: rgba(59,130,246,.2); }
.rc-icon.mindmap { background: rgba(16,185,129,.10); color: #10B981; border-color: rgba(16,185,129,.2); }
.rc-icon.code_example { background: rgba(139,92,246,.10); color: #8B5CF6; border-color: rgba(139,92,246,.2); }
.rc-icon.question_set { background: rgba(245,158,11,.10); color: #F59E0B; border-color: rgba(245,158,11,.2); }
.rc-icon.video_script { background: rgba(59,130,246,.10); color: #3B82F6; border-color: rgba(59,130,246,.2); }
.rc-info { display: flex; flex-direction: column; min-width: 0; }
.rc-type-tag { font-size: 10px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.3px; }
.rc-title { font-size: 13px; font-weight: 500; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.user .rc-title { color: #fff; }
.user .rc-type-tag { color: rgba(255,255,255,.65); }
</style>
