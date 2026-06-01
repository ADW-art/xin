<!--
消息气泡组件

作用：
  渲染单条聊天消息，用户消息和 AI 消息用不同样式区分
  支持 Markdown 渲染（由 marked 库处理）
  流式接收时显示闪烁光标，Agent 切换时显示切换提示条

关联文件：
  views/ChatView.vue  ← 父组件，v-for 遍历消息列表渲染本组件
  stores/chat.ts      ← 读取消息数据（role, content, agent 等）
-->
<template>
  <div :class="['chat-message', role]">
    <div class="avatar" :class="role">
      <el-icon :size="18"><component :is="role === 'user' ? 'User' : 'ChatDotRound'" /></el-icon>
    </div>
    <div class="bubble">
      <div v-if="agentSwitch" class="agent-switch">
        {{ agentSwitch.from }} → {{ agentSwitch.to }}
      </div>
      <div class="content" v-html="rendered" />
      <div v-if="isStreaming" class="cursor">▌</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps<{
  role: string
  content: string
  agent?: string
  agentSwitch?: { from: string; to: string }
  isStreaming?: boolean
}>()

const rendered = computed(() => marked.parse(props.content || '...') as string)
</script>

<style scoped>
.chat-message {
  display: flex;
  gap: 12px;
  padding: 12px 20px;
  max-width: 85%;
}
.chat-message.user {
  flex-direction: row-reverse;
  align-self: flex-end;
  margin-left: auto;
}
.chat-message.assistant {
  align-self: flex-start;
}
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.avatar.assistant {
  background: #ecf5ff;
  color: #409eff;
}
.avatar.user {
  background: #409eff;
  color: #fff;
}
.bubble {
  background: #f5f7fa;
  border-radius: 12px;
  padding: 10px 16px;
  line-height: 1.7;
}
.user .bubble {
  background: #409eff;
  color: #fff;
}
.user .bubble :deep(code) {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}
.agent-switch {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
  padding: 2px 8px;
  background: #e8f0fe;
  border-radius: 4px;
  display: inline-block;
}
.content :deep(pre) {
  background: #2d2d2d;
  color: #e0e0e0;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 13px;
}
.content :deep(code) {
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
}
.content :deep(pre code) {
  background: none;
  padding: 0;
}
.cursor {
  display: inline-block;
  margin-left: 2px;
  animation: blink 1s step-end infinite;
  color: #409eff;
}
@keyframes blink {
  50% { opacity: 0; }
}
</style>
