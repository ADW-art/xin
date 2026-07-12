/*
AudioPlayer — TTS 音频播放器

Props:
  content     — 资源正文 (用于生成 TTS 音频)
  resourceId  — 资源 ID
*/
<template>
  <div class="audio-section">
    <div class="audio-player" :class="{ loading: isLoading, error: !!errorMsg }">
      <button class="play-btn" :disabled="isLoading" @click="togglePlay" :title="isPlaying ? '暂停' : '播放'">
        <svg v-if="isLoading" width="20" height="20" viewBox="0 0 24 24" class="spin">
          <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2.5" stroke-dasharray="47" stroke-dashoffset="31" stroke-linecap="round"/>
        </svg>
        <svg v-else-if="isPlaying" width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="4" width="4" height="16" rx="1"/>
          <rect x="14" y="4" width="4" height="16" rx="1"/>
        </svg>
        <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <polygon points="7,4 20,12 7,20"/>
        </svg>
      </button>

      <div class="audio-info">
        <span class="audio-label">AI 语音讲解</span>
        <div class="progress-bar" v-if="duration > 0">
          <div class="progress-track" @click="seek">
            <div class="progress-fill" :style="{ width: progressPct + '%' }"/>
          </div>
          <span class="time">{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</span>
        </div>
        <span v-else class="audio-hint">点击播放按钮收听语音讲解</span>
      </div>

      <span v-if="errorMsg" class="audio-error">
        <el-icon :size="14"><WarningFilled/></el-icon>
        {{ errorMsg }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  content: string
  resourceId: number
}>()

const audioEl = ref<HTMLAudioElement | null>(null)
const isPlaying = ref(false)
const isLoading = ref(false)
const errorMsg = ref('')
const currentTime = ref(0)
const duration = ref(0)
let _intervalId: ReturnType<typeof setInterval> | null = null

const progressPct = computed(() => {
  if (!duration.value) return 0
  return Math.min(100, (currentTime.value / duration.value) * 100)
})

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function startTick() {
  stopTick()
  _intervalId = setInterval(() => {
    if (audioEl.value) {
      currentTime.value = audioEl.value.currentTime
    }
  }, 250)
}

function stopTick() {
  if (_intervalId) {
    clearInterval(_intervalId)
    _intervalId = null
  }
}

async function getAudioUrl(): Promise<string> {
  const token = localStorage.getItem('token')
  return `/api/resources/${props.resourceId}/audio?token=${token || ''}`
}

async function togglePlay() {
  if (isPlaying.value) {
    audioEl.value?.pause()
    isPlaying.value = false
    stopTick()
    return
  }

  if (audioEl.value && audioEl.value.src && !errorMsg.value) {
    await audioEl.value.play()
    isPlaying.value = true
    startTick()
    return
  }

  isLoading.value = true
  errorMsg.value = ''
  try {
    if (!audioEl.value) {
      audioEl.value = new Audio()
      audioEl.value.addEventListener('ended', () => {
        isPlaying.value = false
        stopTick()
        currentTime.value = 0
      })
      audioEl.value.addEventListener('loadedmetadata', () => {
        duration.value = audioEl.value?.duration || 0
      })
      audioEl.value.addEventListener('error', () => {
        errorMsg.value = '音频加载失败，请稍后重试'
        isLoading.value = false
        isPlaying.value = false
        stopTick()
      })
    }

    const url = await getAudioUrl()
    audioEl.value.src = url
    await audioEl.value.play()
    isPlaying.value = true
    isLoading.value = false
    startTick()
  } catch {
    errorMsg.value = 'TTS 生成失败，请稍后重试'
    isLoading.value = false
  }
}

function seek(e: MouseEvent) {
  if (!audioEl.value || !duration.value) return
  const rect = (e.target as HTMLElement).getBoundingClientRect()
  const pct = (e.clientX - rect.left) / rect.width
  audioEl.value.currentTime = pct * duration.value
}

onBeforeUnmount(() => {
  stopTick()
  if (audioEl.value) {
    audioEl.value.pause()
    audioEl.value.src = ''
  }
})
</script>

<style scoped>
.audio-section {
  margin-top: 0;
}
.audio-player {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: linear-gradient(135deg, rgba(16,185,129,.05), rgba(6,182,212,.05));
  border: 1px solid rgba(16,185,129,.15);
  border-radius: var(--radius-md);
}
.audio-player.error {
  border-color: rgba(239,68,68,.2);
  background: rgba(239,68,68,.04);
}
.play-btn {
  width: 44px; height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #10b981;
  border-radius: 50%;
  background: linear-gradient(135deg, #10b981, #06b6d4);
  color: #fff;
  cursor: pointer;
  flex-shrink: 0;
  transition: all var(--transition-fast);
}
.play-btn:hover:not(:disabled) {
  filter: brightness(1.08);
  box-shadow: 0 2px 10px rgba(16,185,129,.3);
}
.play-btn:disabled {
  opacity: .6;
  cursor: not-allowed;
}
.audio-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.audio-label {
  font-size: var(--font-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.audio-hint {
  font-size: var(--font-xs);
  color: var(--text-muted);
}
.progress-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}
.progress-track {
  flex: 1;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  cursor: pointer;
  min-width: 60px;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #06b6d4);
  border-radius: 2px;
  transition: width .1s linear;
}
.time {
  font-size: 11px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  white-space: nowrap;
}
.audio-error {
  font-size: var(--font-xs);
  color: #DC2626;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }
</style>
