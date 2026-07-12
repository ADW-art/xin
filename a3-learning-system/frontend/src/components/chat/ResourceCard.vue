<!--
  ResourceCard -- 资源卡片组件

  功能：
  - 资源类型图标 + 彩色标签
  - 标题 + 描述摘要
  - 操作按钮："查看详情"（路由跳转）、"朗读"/"视频讲解"
  - 加载骨架屏（animated placeholder）
  - 错误状态（含重试按钮）
  - 悬停浮起 + 边框变色

  Props:
    resourceType   — 资源类型
    resourceTitle  — 资源标题
    resourceId     — 资源 ID
    description    — 内容摘要
    showSlideshow  — 是否显示"视频讲解"按钮
    loading        — 加载中
    error          — 错误消息

  Emits:
    speak         — "朗读"按钮
    slideshow     — "视频讲解"按钮
    generateVideo — "生成视频"按钮（video_script 类型）
    retry         — 错误重试
-->
<template>
  <div class="resource-card" :class="{ 'rc-loading': loading, 'rc-error': !!error }">
    <!-- 加载骨架屏 -->
    <template v-if="loading">
      <div class="rc-left">
        <div class="rc-icon-skel a-shimmer" />
        <div class="rc-info">
          <div class="rc-tag-skel a-shimmer" />
          <div class="rc-title-skel a-shimmer" />
        </div>
      </div>
      <div class="rc-action-skel a-shimmer" />
    </template>

    <!-- 错误状态 -->
    <template v-else-if="error">
      <div class="rc-left">
        <div class="rc-icon err-icon">
          <el-icon :size="20"><WarningFilled /></el-icon>
        </div>
        <div class="rc-info">
          <span class="rc-error-msg">{{ error }}</span>
        </div>
      </div>
      <button class="rc-retry-btn" @click="$emit('retry')">重试</button>
    </template>

    <!-- 正常状态 -->
    <template v-else>
      <div class="rc-left">
        <div class="rc-icon" :class="resolvedType">
          <el-icon :size="22"><component :is="resIcon" /></el-icon>
        </div>
        <div class="rc-info">
          <span class="rc-tag" :class="resolvedType">{{ typeLabel }}</span>
          <span class="rc-title" :title="resourceTitle">{{ resourceTitle }}</span>
          <span v-if="truncatedDescription" class="rc-desc">{{ truncatedDescription }}</span>
        </div>
      </div>
      <div class="rc-actions">
        <button class="rc-action-btn rc-view-btn" @click="goToDetail">
          <el-icon :size="14"><View /></el-icon>
          <span>查看详情</span>
        </button>
        <!-- 视频讲解按钮（仅 document / video_script 类型） -->
        <button v-if="showSlideshow" class="rc-action-btn rc-slideshow-btn" @click="goToSlideshow">
          <el-icon :size="14"><VideoPlay /></el-icon>
          <span>视频讲解</span>
        </button>
        <!-- 生成视频按钮（仅 video_script 类型） -->
        <button v-if="resolvedType === 'video_script'" class="rc-action-btn rc-genvideo-btn" @click="$emit('generateVideo')">
          <el-icon :size="14"><VideoCamera /></el-icon>
          <span>生成视频</span>
        </button>
        <!-- 朗读按钮 -->
        <button v-else class="rc-action-btn rc-speak-btn" @click="$emit('speak')">
          <el-icon :size="14"><Microphone /></el-icon>
          <span>朗读</span>
        </button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { View, Microphone, VideoPlay, WarningFilled, Document, DataBoard, EditPen, Monitor, VideoCamera, Notebook, Headset } from '@element-plus/icons-vue'

const props = defineProps<{
  resourceType: string
  resourceTitle: string
  resourceId: number
  description?: string
  showSlideshow?: boolean
  loading?: boolean
  error?: string
}>()

defineEmits<{
  speak: []
  slideshow: []
  generateVideo: []
  retry: []
}>()

const router = useRouter()

const resolvedType = computed(() => props.resourceType || 'document')

const resIcon = computed(() => {
  const map: Record<string, any> = {
    document: Document,
    mindmap: DataBoard,
    question_set: EditPen,
    video_script: VideoPlay,
    code_example: Monitor,
    notebook: Notebook,
    audio_lecture: Headset,
    video_animation: VideoCamera,
  }
  return map[resolvedType.value] || Document
})

const typeLabel = computed(() => {
  const map: Record<string, string> = {
    document: '知识文档',
    mindmap: '思维导图',
    question_set: '练习题集',
    video_script: '视频脚本',
    code_example: '代码案例',
    notebook: 'Notebook',
    audio_lecture: '语音讲解',
    video_animation: 'AI 视频',
  }
  return map[resolvedType.value] || '学习资源'
})

const truncatedDescription = computed(() => {
  if (!props.description) return ''
  return props.description.length > 100
    ? props.description.slice(0, 100) + '...'
    : props.description
})

function goToDetail() {
  router.push(`/resources/${props.resourceId}`)
}

function goToSlideshow() {
  router.push(`/resources/${props.resourceId}?mode=slideshow`)
}
</script>

<style scoped>
/* Container */
.resource-card {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  box-shadow: var(--shadow-xs);
  transition: all var(--transition-normal) var(--ease-standard);
}
.resource-card:hover {
  box-shadow: var(--shadow-md);
  border-color: #bfdbfe;
  transform: translateY(-1px);
}

:global(.user) .resource-card {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.12);
}
:global(.user) .resource-card:hover {
  border-color: rgba(255, 255, 255, 0.2);
}

/* Left: Icon + Info */
.rc-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}
.rc-icon {
  width: 40px; height: 40px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid;
  transition: transform var(--transition-fast);
}
.resource-card:hover .rc-icon {
  transform: scale(1.05);
}

.rc-icon.document     { background: rgba(37,99,235,.1); color: #2563eb; border-color: rgba(37,99,235,.2); }
.rc-icon.mindmap      { background: rgba(16,185,129,.1); color: #10b981; border-color: rgba(16,185,129,.2); }
.rc-icon.code_example { background: rgba(139,92,246,.1); color: #8b5cf6; border-color: rgba(139,92,246,.2); }
.rc-icon.question_set { background: rgba(245,158,11,.1); color: #f59e0b; border-color: rgba(245,158,11,.2); }
.rc-icon.video_script { background: rgba(59,130,246,.1); color: #3b82f6; border-color: rgba(59,130,246,.2); }

.err-icon {
  background: rgba(239,68,68,.1) !important;
  color: #ef4444 !important;
  border-color: rgba(239,68,68,.2) !important;
}

.rc-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.rc-tag {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.rc-tag.document     { color: #2563eb; }
.rc-tag.mindmap      { color: #10b981; }
.rc-tag.code_example { color: #8b5cf6; }
.rc-tag.question_set { color: #f59e0b; }
.rc-tag.video_script { color: #3b82f6; }
.rc-tag.notebook      { color: #F59E0B; }
.rc-tag.audio_lecture { color: #10B981; }
.rc-tag.video_animation { color: #8B5CF6; }
.rc-title {
  font-size: 13px; font-weight: 600;
  color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rc-desc {
  font-size: 11px; color: var(--text-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 260px;
}
.rc-error-msg { font-size: 12px; color: #ef4444; }

/* Actions */
.rc-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.rc-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: inherit;
  white-space: nowrap;
}
.rc-action-btn:hover {
  background: var(--primary-light);
  border-color: var(--primary);
  color: var(--primary);
}
.rc-view-btn { font-weight: 500; }
.rc-speak-btn { color: var(--text-muted); }
.rc-speak-btn:hover {
  color: #10b981; border-color: #10b981;
  background: rgba(16,185,129,.06);
}
.rc-slideshow-btn { color: var(--text-muted); }
.rc-slideshow-btn:hover {
  color: #3b82f6; border-color: #3b82f6;
  background: rgba(59,130,246,.06);
}
.rc-genvideo-btn { color: var(--text-muted); }
.rc-genvideo-btn:hover {
  color: #10b981; border-color: #10b981;
  background: rgba(16,185,129,.06);
}
.rc-retry-btn {
  padding: 5px 12px;
  border: 1px solid #ef4444;
  border-radius: var(--radius-sm);
  background: rgba(239,68,68,.06);
  color: #ef4444;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}
.rc-retry-btn:hover { background: rgba(239,68,68,.12); }

/* Skeleton */
.rc-icon-skel   { width: 40px; height: 40px; border-radius: var(--radius-md); flex-shrink: 0; }
.rc-tag-skel    { width: 60px; height: 12px; border-radius: 6px; }
.rc-title-skel  { width: 140px; height: 16px; border-radius: 8px; margin-top: 4px; }
.rc-action-skel { width: 80px; height: 28px; border-radius: var(--radius-sm); flex-shrink: 0; }
.rc-loading     { border-color: transparent; box-shadow: none; }
.rc-error       { border-color: rgba(239,68,68,.2); }
</style>
