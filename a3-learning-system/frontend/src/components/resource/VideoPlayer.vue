<!--
  VideoPlayer -- MP4 视频播放器组件

  功能：
  - HTML5 <video> 原生播放器 + 下载按钮
  - 加载态：居中旋转动画 + "视频加载中..."
  - 错误态：错误图标 + 消息 + 重试按钮
  - 空状态：插图 + "暂无视频"
  - 响应式：max-width 100%

  Props:
    videoUrl  — MP4 视频地址（空字符串或 null 显示空状态）
    title     — 视频标题

  Emits:
    retry     — 重试按钮点击
-->
<template>
  <div class="vp-root">
    <!-- 加载态 -->
    <div v-if="loading" class="vp-state vp-loading">
      <el-icon class="vp-spin" :size="32"><Loading /></el-icon>
      <span class="vp-state-text">视频加载中...</span>
    </div>

    <!-- 错误态 -->
    <div v-else-if="error" class="vp-state vp-error">
      <svg viewBox="0 0 120 90" class="vp-svg">
        <rect x="15" y="10" width="90" height="55" rx="8" fill="rgba(239,68,68,.08)" stroke="rgba(239,68,68,.2)" stroke-width="1.5"/>
        <circle cx="60" cy="38" r="12" fill="rgba(239,68,68,.1)" stroke="rgba(239,68,68,.25)" stroke-width="1"/>
        <path d="M55 33l10 10M65 33l-10 10" stroke="#EF4444" stroke-width="1.8" stroke-linecap="round"/>
        <rect x="30" y="72" width="60" height="4" rx="2" fill="rgba(255,255,255,.06)"/>
      </svg>
      <span class="vp-state-text vp-err-text">{{ error }}</span>
      <el-button size="small" type="primary" @click="retryVideo">
        <el-icon :size="14"><Refresh /></el-icon> 重试
      </el-button>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!videoUrl" class="vp-state vp-empty">
      <svg viewBox="0 0 120 90" class="vp-svg">
        <rect x="15" y="10" width="90" height="55" rx="8" fill="rgba(37,99,235,.04)" stroke="rgba(37,99,235,.12)" stroke-width="1.2"/>
        <polygon points="48,24 48,50 72,37" fill="rgba(37,99,235,.15)" stroke="rgba(37,99,235,.2)" stroke-width="1"/>
        <rect x="30" y="72" width="60" height="4" rx="2" fill="rgba(255,255,255,.06)"/>
        <rect x="40" y="80" width="40" height="3" rx="1.5" fill="rgba(255,255,255,.04)"/>
      </svg>
      <span class="vp-state-text">暂无视频</span>
    </div>

    <!-- 正常态：视频播放 -->
    <div v-else class="vp-data">
      <div class="vp-header">
        <div class="vp-title-row">
          <el-icon :size="18" class="vp-title-icon"><VideoCamera /></el-icon>
          <h3 class="vp-title">{{ title }}</h3>
        </div>
        <el-button size="small" plain @click="downloadVideo">
          <el-icon :size="14"><Download /></el-icon> 下载 MP4
        </el-button>
      </div>
      <div class="vp-video-wrap">
        <video
          ref="videoRef"
          class="vp-video"
          controls
          controlsList="nodownload"
          preload="metadata"
          @loadeddata="onLoaded"
          @error="onVideoError"
        >
          <source :src="videoUrl" type="video/mp4" />
          您的浏览器不支持 HTML5 视频播放。
        </video>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Loading, Refresh, VideoCamera, Download } from '@element-plus/icons-vue'

const props = defineProps<{
  videoUrl: string
  title?: string
}>()

const emit = defineEmits<{
  retry: []
}>()

const loading = ref(true)
const error = ref('')
const videoRef = ref<HTMLVideoElement | null>(null)

// 每次 videoUrl 变化时重置状态
watch(() => props.videoUrl, (url) => {
  if (url) {
    loading.value = true
    error.value = ''
  } else {
    loading.value = false
    error.value = ''
  }
})

function onLoaded() {
  loading.value = false
  error.value = ''
}

function onVideoError() {
  loading.value = false
  error.value = '视频加载失败，请检查网络或稍后重试'
}

function retryVideo() {
  const el = videoRef.value
  if (el) {
    loading.value = true
    error.value = ''
    el.load()
  } else {
    emit('retry')
  }
}

function downloadVideo() {
  if (!props.videoUrl) return
  const a = document.createElement('a')
  a.href = props.videoUrl
  a.download = `${props.title || '学习视频'}.mp4`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
</script>

<style scoped>
/* ── 根容器 ── */
.vp-root {
  width: 100%;
  max-width: 100%;
}

/* ── 状态共享 ── */
.vp-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 24px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  text-align: center;
  min-height: 180px;
}

.vp-state-text {
  font-size: var(--font-sm);
  color: var(--text-secondary);
}

.vp-svg {
  width: 120px;
  height: 90px;
  opacity: .65;
}

/* ── 加载态 ── */
.vp-loading {
  color: var(--text-secondary);
}
.vp-spin {
  animation: vp-spin 1s linear infinite;
  color: var(--primary);
}
@keyframes vp-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ── 错误态 ── */
.vp-err-text {
  color: #EF4444;
}

/* ── 空状态 ── */
.vp-empty .vp-state-text {
  color: var(--text-muted);
}

/* ── 正常态：播放器 ── */
.vp-data {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.vp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-page);
}

.vp-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.vp-title-icon {
  color: var(--primary);
  flex-shrink: 0;
}

.vp-title {
  font-size: var(--font-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vp-video-wrap {
  position: relative;
  background: #000;
}

.vp-video {
  display: block;
  width: 100%;
  max-width: 100%;
  outline: none;
  aspect-ratio: 16 / 9;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .vp-state {
    padding: 32px 16px;
    min-height: 140px;
  }
  .vp-header {
    padding: 10px 14px;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  .vp-title {
    font-size: var(--font-sm);
  }
}

@media (max-width: 480px) {
  .vp-state {
    padding: 24px 12px;
    min-height: 120px;
    gap: 8px;
  }
  .vp-svg {
    width: 90px;
    height: 68px;
  }
  .vp-header {
    padding: 8px 10px;
  }
}
</style>
