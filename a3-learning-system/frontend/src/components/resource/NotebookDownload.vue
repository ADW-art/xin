/*
NotebookDownload — Jupyter Notebook 导出组件

Props:
  content — 资源正文 (markdown)
  title   — 资源标题
  resourceId — 资源 ID
*/
<template>
  <div class="notebook-section">
    <div class="notebook-header">
      <div class="notebook-info">
        <span class="notebook-badge">Jupyter Notebook</span>
        <span class="notebook-stats">
          <span class="stat">{{ codeCellCount }} 个代码块</span>
          <span class="stat-sep">|</span>
          <span class="stat">{{ textCellCount }} 个说明段落</span>
        </span>
      </div>
      <button class="download-btn" :class="{ loading: downloading }" :disabled="downloading" @click="download">
        <svg v-if="!downloading" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        <el-icon v-else :size="14" class="spin"><Loading/></el-icon>
        <span>{{ downloading ? '正在生成...' : '下载 .ipynb' }}</span>
      </button>
    </div>

    <!-- 内容预览 -->
    <div class="notebook-preview markdown-body" v-html="renderedPreview"/>

    <!-- 错误提示 -->
    <div v-if="errorMsg" class="notebook-error">
      <el-icon :size="14"><WarningFilled/></el-icon>
      {{ errorMsg }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, WarningFilled } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps<{
  content: string
  title: string
  resourceId: number
}>()

const downloading = ref(false)
const errorMsg = ref('')

const codeCellCount = computed(() => {
  const matches = props.content.match(/```(?:python|python3|py)?\s*\n/g)
  return matches ? matches.length : 0
})

const textCellCount = computed(() => {
  const parts = props.content.split(/```[\s\S]*?```/)
  return parts.filter(p => p.trim().length > 0).length
})

const renderedPreview = computed(() => {
  try {
    return DOMPurify.sanitize(marked.parse(props.content) as string, {
      ALLOWED_ATTR: ['class', 'href', 'target', 'id', 'style'],
      ALLOWED_TAGS: ['a', 'b', 'i', 'em', 'strong', 'p', 'br', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'code', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'span', 'div'],
    })
  } catch {
    return props.content.replace(/</g, '&lt;').replace(/>/g, '&gt;')
  }
})

async function download() {
  downloading.value = true
  errorMsg.value = ''
  try {
    const token = localStorage.getItem('token')
    const res = await fetch(`/api/resources/${props.resourceId}/export/notebook`, {
      headers: token ? { Authorization: 'Bearer ' + token } : {},
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '下载失败' }))
      throw new Error(err.detail || '下载失败')
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = (props.title || 'notebook').replace(/\s+/g, '_') + '.ipynb'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('Notebook 已下载')
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '下载失败，请稍后重试'
    errorMsg.value = msg
  } finally {
    downloading.value = false
  }
}
</script>

<style scoped>
.notebook-section {
  margin-top: 0;
}
.notebook-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  background: linear-gradient(135deg, rgba(245,158,11,.06), rgba(249,115,22,.06));
  border: 1px solid rgba(245,158,11,.18);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.notebook-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.notebook-badge {
  font-size: var(--font-sm);
  font-weight: 700;
  color: #F59E0B;
}
.notebook-stats {
  font-size: var(--font-xs);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 6px;
}
.stat-sep {
  color: var(--border);
}
.download-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border: 1px solid #F59E0B;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, #F59E0B, #F97316);
  color: #fff;
  font-size: var(--font-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: inherit;
  white-space: nowrap;
}
.download-btn:hover:not(:disabled) {
  filter: brightness(1.08);
  box-shadow: 0 2px 8px rgba(245,158,11,.3);
}
.download-btn:disabled {
  opacity: .7;
  cursor: not-allowed;
}
.notebook-preview {
  line-height: 1.85;
  color: var(--text-primary);
}
.notebook-preview :deep(h1) { font-size: var(--font-2xl); font-weight: 700; margin: 28px 0 14px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.notebook-preview :deep(h2) { font-size: var(--font-xl); font-weight: 700; margin: 24px 0 12px; }
.notebook-preview :deep(h3) { font-size: var(--font-lg); font-weight: 600; margin: 20px 0 10px; }
.notebook-preview :deep(pre) { background: #1E293B; color: #E2E8F0; border-radius: var(--radius-md); padding: 18px 20px; overflow-x: auto; margin: 14px 0; border: 1px solid #334155; }
.notebook-preview :deep(pre code) { background: none; padding: 0; font-size: var(--font-sm); line-height: 1.65; }
.notebook-preview :deep(code) { background: var(--bg-muted); color: var(--text-primary); padding: 2px 6px; border-radius: var(--radius-sm); font-size: 13px; font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace; }
.notebook-error {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #DC2626;
  font-size: var(--font-xs);
}
.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }
</style>
