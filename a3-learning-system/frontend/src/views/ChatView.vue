<!--
对话页面（核心）

作用：
  聊天对话主界面，是整个前端最核心的页面
  整合 ChatInput（输入框）、ChatMessage（消息气泡）、Pinia store（状态管理）
  通过 SSE 流式接口与后端多 Agent 系统交互

关联文件：
  stores/chat.ts              ← 管理消息列表和流式状态
  api/chat.ts                 ← 调用 SSE 流式接口
  components/chat/ChatInput   ← 底部输入框组件
  components/chat/ChatMessage ← 消息气泡组件
  router/index.ts             ← 路由配置：/chat 指向本页面

交互流程：
  用户输入 → handleSend() → addUserMessage() → startAssistantReply()
  → sendMessageStream() → SSE 流式接收 → appendToStreaming() → 打字机效果
-->
<template>
  <div class="chat-view">
    <div class="message-list" ref="listRef">
      <ChatMessage
        v-for="msg in store.messages"
        :key="msg.id"
        :role="msg.role"
        :content="msg.content"
        :agent="msg.agent"
        :agent-switch="msg.agentSwitch"
        :is-streaming="msg.id === streamingId && store.isStreaming"
      />
      <div v-if="store.messages.length === 0" class="empty">
        <div class="empty-icon"><el-icon :size="48"><ChatDotRound /></el-icon></div>
        <h3>开始对话</h3>
        <p>向 AI 学习助手提问，获取个性化帮助</p>
      </div>
    </div>
    <ChatInput :disabled="store.isStreaming" @send="handleSend" />
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat'
import { sendMessageStream } from '@/api/chat'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import ChatInput from '@/components/chat/ChatInput.vue'

const store = useChatStore()
const listRef = ref<HTMLElement>()
const streamingId = ref('')

function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) {
      listRef.value.scrollTop = listRef.value.scrollHeight
    }
  })
}

let abortController: AbortController | null = null

function handleSend(content: string) {
  if (store.isStreaming) return

  store.addUserMessage(content)
  scrollToBottom()
  store.startAssistantReply()
  streamingId.value = store.messages[store.messages.length - 1].id

  abortController = sendMessageStream(
    content,
    (data) => {
      if (data.from && data.to) {
        store.setAgentSwitch(data.from, data.to)
      }
      store.appendToStreaming(data.content || '', data.agent)
      scrollToBottom()
    },
    () => {
      store.finishAssistantReply()
      streamingId.value = ''
      scrollToBottom()
    },
    (err) => {
      store.appendToStreaming(`错误: ${err.message}`)
      store.finishAssistantReply()
      streamingId.value = ''
    }
  )
}
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px);
  max-width: 900px;
  margin: 0 auto;
}
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  display: flex;
  flex-direction: column;
}
.empty {
  text-align: center;
  color: #909399;
  margin-top: 120px;
}
.empty-icon {
  margin-bottom: 16px;
  color: #c0c4cc;
}
.empty h3 {
  font-size: 18px;
  color: #606266;
  margin-bottom: 8px;
}
.empty p {
  margin: 0;
  font-size: 14px;
}
</style>
