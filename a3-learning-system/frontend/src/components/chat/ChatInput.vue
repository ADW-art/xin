<!--
消息输入框组件

作用：
  提供文本输入和发送功能
  Enter 发送消息，Shift+Enter 换行
  流式接收时自动禁用输入

关联文件：
  views/ChatView.vue  ← 父组件，监听 @send 事件处理消息发送
  stores/chat.ts      ← 读取 isStreaming 状态控制禁用
-->
<template>
  <div class="chat-input">
    <el-input
      v-model="text"
      type="textarea"
      :rows="2"
      placeholder="输入消息，Shift+Enter 换行，Enter 发送"
      :disabled="disabled"
      resize="none"
      @keydown.enter.exact.prevent="send"
    />
    <el-button type="primary" :disabled="!text.trim() || disabled" @click="send">
      发送
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ send: [content: string] }>()

const text = ref('')

function send() {
  const content = text.value.trim()
  if (!content || props.disabled) return
  emit('send', content)
  text.value = ''
}
</script>

<style scoped>
.chat-input {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #e4e7ed;
  background: #fff;
}
.chat-input :deep(.el-textarea__inner) {
  font-size: 15px;
}
</style>
