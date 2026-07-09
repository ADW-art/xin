<template>
  <div class="chat-input" @dragover.prevent="onDragOver" @dragleave="onDragLeave" @drop.prevent="onDrop">
    <div class="input-wrap">
      <!-- 图片预览区 -->
      <div v-if="images.length > 0" class="image-preview-bar">
        <div v-for="(img, idx) in images" :key="idx" class="img-preview-item">
          <img :src="img.url" :alt="'图片'+(idx+1)" />
          <button class="img-remove-btn" @click.stop="removeImage(idx)" title="移除图片">&times;</button>
        </div>
        <span class="img-hint">{{ images.length }} 张图片</span>
      </div>

      <el-input
        v-model="text"
        type="textarea"
        :rows="2"
        placeholder="输入消息... (支持粘贴截图 / 拖拽图片)"
        :disabled="disabled"
        :maxlength="maxChars"
        aria-label="输入消息"
        resize="none"
        class="chat-textarea"
        @keydown.enter.exact.prevent="send"
        @paste="onPaste"
        show-word-limit
      />
      <div class="input-footer">
        <div class="input-actions">
          <!-- 图片上传按钮 -->
          <label class="action-btn" title="上传图片">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
            </svg>
            <input ref="fileInputRef" type="file" accept="image/*" multiple class="hidden-file-input" @change="onFileSelect" />
          </label>
          <span class="char-count" :class="{ near: text.length > maxChars * 0.8 }">{{ text.length }}/{{ maxChars }}</span>
        </div>
        <span class="kb-hint">Enter 发送 &middot; Shift+Enter 换行 &middot; Ctrl+V 粘贴图片</span>
      </div>
    </div>
    <el-button
      type="primary"
      :disabled="(!text.trim() && images.length === 0) || disabled"
      @click="send"
      class="send-btn"
      :title="disabled ? '正在生成回复...' : '发送消息 (Enter)'"
      :aria-label="disabled ? '正在生成回复' : '发送消息'"
    >
      <svg v-if="!disabled" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
      </svg>
      <span v-if="!disabled" class="send-text">发送</span>
      <span v-else class="send-text">生成中</span>
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

interface ImageItem {
  url: string       // base64 data URL 或 blob URL
  base64?: string   // 纯 base64 数据（用于发送后端）
  name: string
  size: number
  type: string
}

const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ send: [content: string, images?: ImageItem[]] }>()

const text = ref('')
const maxChars = 4000
const images = ref<ImageItem[]>([])
const fileInputRef = ref<HTMLInputElement>()

// ── 最大图片限制 ──
const MAX_IMAGES = 4
const MAX_IMAGE_SIZE_MB = 10

// ── 图片处理：File → base64 ──
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

// ── 图片压缩（客户端压缩大图）──
const COMPRESS_THRESHOLD = 2 * 1024 * 1024 // 2MB
const COMPRESS_QUALITY = 0.8
const COMPRESS_MAX_WIDTH = 1920

async function compressImage(file: File): Promise<{ dataUrl: string; base64: string; compressed: boolean }> {
  if (file.size <= COMPRESS_THRESHOLD) {
    const dataUrl = await fileToBase64(file)
    return { dataUrl, base64: dataUrl.split(',')[1] || '', compressed: false }
  }

  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      let { width, height } = img

      // 缩放逻辑：保持宽高比，最大宽度限制
      if (width > COMPRESS_MAX_WIDTH) {
        height = (height * COMPRESS_MAX_WIDTH) / width
        width = COMPRESS_MAX_WIDTH
      }

      canvas.width = width
      canvas.height = height

      const ctx = canvas.getContext('2d')
      if (!ctx) { reject(new Error('Canvas context error')); return }

      ctx.drawImage(img, 0, 0, width, height)
      const dataUrl = canvas.toDataURL(file.type || 'image/jpeg', COMPRESS_QUALITY)
      resolve({ dataUrl, base64: dataUrl.split(',')[1] || '', compressed: true })
    }
    img.onerror = reject
    img.src = URL.createObjectURL(file)
  })
}

// ── 添加图片（统一入口）──
async function addImages(files: FileList | File[]) {
  const fileArr = Array.from(files).filter(f => f.type.startsWith('image/'))
  if (fileArr.length === 0) return

  // 超量检查
  const remaining = MAX_IMAGES - images.value.length
  if (remaining <= 0) return

  for (const file of fileArr.slice(0, remaining)) {
    // 大小检查 (MB)
    const sizeMB = file.size / (1024 * 1024)
    if (sizeMB > MAX_IMAGE_SIZE_MB) {
      ElMessage.warning(`图片 "${file.name}" 超过 ${MAX_IMAGE_SIZE_MB}MB 限制，已跳过`)
      continue
    }

    try {
      const { dataUrl, base64, compressed } = await compressImage(file)
      if (compressed) {
        ElMessage.info(`图片 "${file.name}" 已压缩以提升传输效率`)
      }
      images.value.push({
        url: dataUrl,
        base64: base64,
        name: file.name,
        size: file.size,
        type: file.type,
      })
    } catch {
      if (import.meta.env.DEV) console.error('图片读取失败:', file.name)
    }
  }
}

// ── 移除单张图片 ──
function removeImage(idx: number) {
  images.value.splice(idx, 1)
}

// ── 粘贴事件（Ctrl+V 粘贴截图）──
async function onPaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return

  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.type.startsWith('image/')) {
      e.preventDefault()
      const file = item.getAsFile()
      if (file) await addImages([file])
      break
    }
  }
}

// ── 文件选择按钮 ──
function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) addImages(input.files)
  input.value = '' // 重置以允许重复选择同一文件
}

// ── 拖拽事件 ──
function onDragOver(e: DragEvent) {
  ;(e.currentTarget as HTMLElement).classList.add('drag-over')
}
function onDragLeave(e: DragEvent) {
  ;(e.currentTarget as HTMLElement).classList.remove('drag-over')
}
async function onDrop(e: DragEvent) {
  ;(e.currentTarget as HTMLElement).classList.remove('drag-over')
  if (e.dataTransfer?.files) await addImages(e.dataTransfer.files)
}

// ── 发送 ──
function send() {
  const content = text.value.trim()
  if (!content && images.value.length === 0 || props.disabled) return

  const imgsToSend = images.value.length > 0 ? [...images.value] : undefined
  emit('send', content, imgsToSend)

  // 清空
  text.value = ''
  images.value = []
}

// ── 暴露方法供父组件调用 ──
defineExpose({ clear: () => { text.value = ''; images.value = [] } })
</script>

<style scoped>
.chat-input {
  display: flex;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--border);
  background: rgba(255,255,255,.9);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  align-items: flex-end;
  flex-shrink: 0;
  transition: border-color 0.2s;
}
.chat-input.drag-over {
  border-top-color: #2563EB;
  background: rgba(237,242,255,.95);
}
.chat-input.drag-over .chat-textarea :deep(.el-textarea__inner) {
  border-color: #2563EB !important;
  box-shadow: 0 0 0 3px rgba(37,99,235,.12) !important;
}

.input-wrap {
  flex: 1;
  position: relative;
}

/* ── 图片预览条 ── */
.image-preview-bar {
  display: flex;
  gap: 6px;
  padding: 6px 0;
  flex-wrap: wrap;
  align-items: center;
}
.img-preview-item {
  position: relative;
  width: 56px;
  height: 56px;
  border-radius: 8px;
  overflow: hidden;
  border: 1.5px solid var(--border);
  flex-shrink: 0;
  transition: border-color 0.15s;
}
.img-preview-item:hover { border-color: #2563EB; }
.img-preview-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.img-remove-btn {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #EF4444;
  color: white;
  border: none;
  font-size: 12px;
  line-height: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  opacity: 0;
  transition: opacity 0.15s;
}
.img-preview-item:hover .img-remove-btn { opacity: 1; }
.img-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: auto;
}

/* ── Textarea ── */
.chat-input :deep(.el-textarea__inner) {
  font-size: 15px;
  background: var(--bg-input) !important;
  border-color: var(--border) !important;
  color: var(--text-primary) !important;
  border-radius: var(--radius-md) !important;
  transition: all var(--transition-normal) var(--ease-standard) !important;
  padding: 10px 14px !important;
  line-height: 1.5;
  box-shadow: none !important;
}
.chat-input :deep(.el-textarea__inner):hover {
  border-color: var(--border) !important;
  background: var(--bg-card) !important;
}
.chat-input :deep(.el-textarea__inner):focus {
  border-color: var(--border-focus) !important;
  box-shadow: 0 0 0 3px rgba(37,99,235,.1) !important;
}
.chat-input :deep(.el-textarea__inner::placeholder) {
  color: var(--text-muted);
  font-size: 14px;
}

/* ── Input footer ── */
.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 5px;
  padding: 0 2px;
}
.input-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-muted);
  transition: all 0.15s;
  border: 1px solid transparent;
}
.action-btn:hover {
  color: #2563EB;
  background: rgba(37,99,235,.06);
  border-color: rgba(37,99,235,.15);
}
.hidden-file-input { display: none; }
.char-count {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
  transition: color 0.2s;
}
.char-count.near { color: #60A5FA; font-weight: 600; }
.kb-hint {
  font-size: 11px;
  color: var(--text-muted);
  opacity: 0.6;
  transition: opacity 0.2s;
}
.input-wrap:focus-within .kb-hint { opacity: 1; }

/* ── Send Button ── */
.send-btn {
  height: 44px;
  min-width: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: var(--radius-md) !important;
  transition: all var(--transition-normal) var(--ease-standard) !important;
  flex-shrink: 0;
  position: relative;
  overflow: hidden;
}
.send-btn:not(:disabled):hover { box-shadow: var(--shadow-lg) !important; }
.send-btn:not(:disabled):active { transform: translateY(0); }
.send-btn:disabled { opacity: 0.45; cursor: not-allowed; filter: grayscale(0.3); }
.send-text { font-size: 14px; font-weight: 700; letter-spacing: 0.3px; }

@media (max-width: 480px) {
  .chat-input { padding: 10px 12px; }
  .send-text { display: none; }
  .send-btn { min-width: 44px; height: 44px; border-radius: 50% !important; }
  .kb-hint { display: none; }
  .img-preview-item { width: 48px; height: 48px; }
}
</style>
