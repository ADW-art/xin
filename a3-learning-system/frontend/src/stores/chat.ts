
/*
对话状态管理（Pinia Store）

作用：
  管理聊天对话的所有状态，包括消息列表、流式接收状态、Agent 切换
  提供操作方法：添加消息、追加流式内容、处理 Agent 切换等

关联文件：
  views/ChatView.vue      ← 使用本 store 管理聊天数据和状态
  components/chat/        ← ChatMessage 和 ChatInput 读取 store 中的数据
  api/chat.ts             ← SSE 回调函数调用本 store 的方法更新状态
*/
import { defineStore } from 'pinia'   // Pinia：Vue3 状态管理，类似 Vuex
import { ref } from 'vue'             // ref：创建响应式数据

// 单条消息的数据结构
export interface ChatMessage {
  id: string                          // 消息唯一 ID（用 crypto.randomUUID() 生成）
  role: 'user' | 'assistant'          // 消息角色：用户还是 AI
  content: string                     // 消息文本内容（Markdown 格式）
  images?: string[]                   // 用户消息中的图片（data URL 列表）— 多模态
  agent?: string                      // 产生此消息的 Agent 名称
  agentSwitch?: { from: string; to: string }  // Agent 切换信息（显示切换提示）
  resourceType?: string               // 生成的资源类型（mindmap/code_example/document/question_set/video_script）
  resourceId?: number                 // 生成的资源ID
  resourceTitle?: string              // 生成的资源标题
  createdAt: number                   // 创建时间戳（Date.now()）
}

// defineStore('store名', 函数) → 创建 Pinia Store
export const useChatStore = defineStore('chat', () => {
  // ============ 响应式状态 ============
  const messages = ref<ChatMessage[]>([])   // 消息列表（响应式，变化时自动更新 UI）
  const isStreaming = ref(false)            // 是否正在接收流式响应
  const currentAgent = ref('supervisor')    // 当前活跃的 Agent 名
  let streamingMsgId = ''                   // 当前正在流式接收的消息 ID（非响应式，内部使用）

  // ============ 操作方法 ============

  // 添加用户消息到列表
  function addUserMessage(content: string, images?: string[]) {
    messages.value.push({
      id: crypto.randomUUID(),             // 生成全局唯一 ID
      role: 'user',
      content,
      images,                               // 多模态图片
      createdAt: Date.now(),
    })
  }

  // 开始接收 AI 回复：创建一条空的占位消息
  function startAssistantReply() {
    streamingMsgId = crypto.randomUUID()   // 为这条回复生成唯一 ID
    isStreaming.value = true               // 标记正在流式接收
    messages.value.push({
      id: streamingMsgId,
      role: 'assistant',
      content: '',                         // 初始为空，后续追加内容
      agent: currentAgent.value,
      createdAt: Date.now(),
    })
  }

  // 追加内容到当前正在流式接收的消息（打字机效果）
  function appendToStreaming(content: string, agent?: string) {
    const msg = messages.value.find((m) => m.id === streamingMsgId)
    if (msg) {
      msg.content += content               // 每次只在末尾追加新的一段
      if (agent) msg.agent = agent
    }
  }

  // 记录 Agent 切换
  function setAgentSwitch(from: string, to: string) {
    currentAgent.value = to                // 更新当前 Agent
    const msg = messages.value.find((m) => m.id === streamingMsgId)
    if (msg) {
      msg.agentSwitch = { from, to }       // 保存切换信息（显示切换提示条）
      msg.agent = to
    }
  }

  // 结束流式接收
  function finishAssistantReply() {
    isStreaming.value = false              // 关闭流式状态
    streamingMsgId = ''                    // 清空当前消息 ID
  }

  // 将资源信息附加到当前流式消息上
  function setResource(resourceType: string, resourceId: number, resourceTitle: string) {
    const msg = messages.value.find((m) => m.id === streamingMsgId)
    if (msg) {
      msg.resourceType = resourceType
      msg.resourceId = resourceId
      msg.resourceTitle = resourceTitle
      if (!msg.agent) msg.agent = 'resource_agent'
    }
  }

  // 清空所有消息
  function clearMessages() {
    messages.value = []
  }

  // ============ 暴露给外部的属性和方法 ============
  return {
    messages,
    isStreaming,
    currentAgent,
    addUserMessage,
    startAssistantReply,
    appendToStreaming,
    setAgentSwitch,
    setResource,
    finishAssistantReply,
    clearMessages,
  }
})
