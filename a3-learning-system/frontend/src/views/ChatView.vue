<template>
  <div class="chat-layout">
    <!-- 对话历史抽屉 -->
    <el-drawer
      v-model="sidebarOpen"
      direction="ltr"
      :size="300"
      :with-header="false"
      :append-to-body="true"
      :modal="true"
    >
      <div class="drawer-inner">
        <div class="drawer-header">
          <span class="drawer-title">对话历史</span>
          <div class="drawer-actions">
            <el-button type="primary" size="small" @click="handleNewChat" :disabled="store.isStreaming">
              <el-icon><Plus /></el-icon> 新建对话
            </el-button>
            <el-button
              type="danger"
              size="small"
              plain
              @click="clearAllHistory"
              :disabled="store.isStreaming || groupedHistory.length === 0"
            >
              <el-icon><Delete /></el-icon> 清空全部
            </el-button>
          </div>
        </div>

        <div v-if="historyLoading" class="sb-state">
          <el-icon class="spinner"><Loading /></el-icon>
        </div>
        <div v-else-if="historyError" class="sb-state error">
          <span>{{ historyError }}</span>
          <el-button size="small" text @click="fetchHistory">重试</el-button>
        </div>
        <div v-else-if="groupedHistory.length === 0" class="sb-state">
          <span>暂无历史对话</span>
        </div>
        <div v-else class="history-list">
          <div
            v-for="convo in groupedHistory"
            :key="convo.id"
            :class="['history-item', { active: convo.id === activeConvoId }]"
            @click="loadConversation(convo)"
          >
            <div class="hi-header">
              <span class="hi-date">{{ convo.dateLabel }}</span>
              <span v-if="convo.agentType" class="hi-agent" :style="{ color: agentColor(convo.agentType) }">
                {{ convo.agentType }}
              </span>
              <el-button
                text
                size="small"
                class="hi-delete-btn"
                @click.stop="deleteConversation(convo)"
                :loading="convo._deleting"
              >
                <el-icon :size="14"><Close /></el-icon>
              </el-button>
            </div>
            <div class="hi-text">{{ convo.preview }}</div>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- ══ 顶部工具栏 ══ -->
    <div class="chat-topbar">
      <el-button text class="history-toggle-btn" @click="sidebarOpen = true" aria-label="打开对话历史">
        <el-icon :size="18"><Clock /></el-icon>
        <span>对话历史</span>
      </el-button>
      <div class="topbar-right">
        <!-- 停止生成按钮 -->
        <el-button
          v-if="store.isStreaming && abortCtrl"
          size="small"
          type="warning"
          plain
          class="stop-btn"
          @click="handleStop"
          aria-label="停止生成"
        >
          <el-icon :size="14"><Close /></el-icon>
          停止生成
        </el-button>
        <div class="topbar-status">
          <span class="status-dot" :class="{ generating: store.isStreaming }"></span>
          <span class="status-text">{{ store.isStreaming ? '生成中...' : 'AI 在线' }}</span>
        </div>
      </div>
    </div>

    <!-- ══ 进度条（Agent生成资源时显示） ══ -->
    <transition name="progress-fade">
      <div v-if="progressVisible" class="progress-bar-wrap">
        <div class="progress-info">
          <span class="progress-agent">{{ progressAgent }}</span>
          <span class="progress-msg">{{ progressMessage || '正在处理...' }}</span>
        </div>
        <el-progress
          :percentage="progressPercent"
          :stroke-width="3"
          :show-text="true"
          :color="progressColor"
          class="progress-bar"
        />
      </div>
    </transition>

    <!-- ══ 消息列表（弹性占据剩余空间） ══ -->
    <div class="messages" ref="listRef" @scroll="onScroll">
      <!-- 空状态：更好的欢迎界面 -->
      <div v-if="store.messages.length === 0" class="empty">
        <div class="empty-icon">
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            <line x1="9" y1="10" x2="15" y2="10"/><line x1="12" y1="7" x2="12" y2="13"/>
          </svg>
        </div>
        <h3>你好，我是 A3 学习助手</h3>
        <p>基于多智能体协作，为你提供个性化学习支持</p>
        <div class="empty-features">
          <div class="feature-item">
            <el-icon :size="20"><User /></el-icon>
            <div><strong>画像采集</strong><span>了解你的学习风格与目标</span></div>
          </div>
          <div class="feature-item">
            <el-icon :size="20"><Reading /></el-icon>
            <div><strong>资源生成</strong><span>个性化知识文档与思维导图</span></div>
          </div>
          <div class="feature-item">
            <el-icon :size="20"><TrendCharts /></el-icon>
            <div><strong>学习评估</strong><span>BKT知识追踪与能力分析</span></div>
          </div>
          <div class="feature-item">
            <el-icon :size="20"><Guide /></el-icon>
            <div><strong>路径规划</strong><span>知识图谱驱动的学习路线</span></div>
          </div>
        </div>
        <div class="empty-suggestions">
          <span class="suggestion-tag" @click="quickAsk('帮我制定一个 Python 学习计划')">
            <el-icon :size="14"><Monitor /></el-icon> Python 学习计划
          </span>
          <span class="suggestion-tag" @click="quickAsk('评估一下我的学习情况')">
            <el-icon :size="14"><TrendCharts /></el-icon> 学习评估
          </span>
          <span class="suggestion-tag" @click="quickAsk('出几道算法题练练手')">
            <el-icon :size="14"><EditPen /></el-icon> 算法练习
          </span>
          <span class="suggestion-tag" @click="quickAsk('介绍一下你自己的功能')">
            <el-icon :size="14"><InfoFilled /></el-icon> 功能介绍
          </span>
        </div>
      </div>

      <!-- 消息列表 -->
      <template v-for="(msg, idx) in store.messages" :key="msg.id">
        <ChatMessage
          :role="msg.role"
          :content="msg.content"
          :images="msg.images"
          :agent="msg.agent"
          :agent-switch="msg.agentSwitch"
          :is-streaming="msg.id === streamingId && store.isStreaming"
          :resource-type="msg.resourceType"
          :resource-id="msg.resourceId"
          :resource-title="msg.resourceTitle"
          :class="['msg-enter', { 'msg-streaming': msg.id === streamingId && store.isStreaming }]"
          :style="{ animationDelay: idx < 2 ? '0ms' : Math.min(idx * 50, 300) + 'ms' }"
        />
        <!-- Re-generate button for last assistant message (only when not streaming) -->
        <div v-if="msg.role === 'assistant' && idx === store.messages.length - 1 && !store.isStreaming && msg.content" class="regenerate-wrap">
          <el-button text size="small" class="regenerate-btn" @click="regenerate(msg, idx)">
            <el-icon :size="14"><Refresh /></el-icon> 重新生成
          </el-button>
        </div>
      </template>

      <!-- 回到底部按钮 -->
      <transition name="scroll-fade">
        <button v-if="showScrollBtn" class="scroll-bottom-btn" aria-label="滚动到底部" @click="scrollToBottom">
          <el-icon :size="18"><ArrowDown /></el-icon>
        </button>
      </transition>
    </div>

    <!-- ══ 输入框（固定底部） ══ -->
    <ChatInput :disabled="store.isStreaming" @send="handleSend" />
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { sendMessageStream } from '@/api/chat'
import type { SSEChunk, SendImage } from '@/api/chat'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import api from '@/api/index'
import dayjs from 'dayjs'

interface HistoryItem {
  id: number
  role: string
  content: string
  agent_type: string | null
  created_at: string
}

interface ConvoGroup {
  id: number
  userMessage: string
  assistantMessage: string
  agentType: string | null
  createdAt: string
  dateLabel: string
  preview: string
  messageIds?: number[]
  _deleting?: boolean
}

const store = useChatStore()
const listRef = ref<HTMLElement>()
const streamingId = ref('')

const sidebarOpen = ref(false)
const historyLoading = ref(false)
const historyError = ref('')
const historyItems = ref<HistoryItem[]>([])
const activeConvoId = ref<number | null>(null)
const groupedHistory = ref<ConvoGroup[]>([])
let _fetchingHistory = false  // 防止并发重复请求
let _sending = false  // 防止快速重复发送
const SEND_COOLDOWN = 800 // 发送冷却时间(ms)

// ── AbortController: 停止生成 ──
const abortCtrl = ref<AbortController | null>(null)

function handleStop() {
  if (abortCtrl.value) {
    abortCtrl.value.abort()
    abortCtrl.value = null
    store.finishAssistantReply()
    streamingId.value = ''
    progressVisible.value = false
  }
}

// ── Progress bar state ──
const progressVisible = ref(false)
const progressAgent = ref('')
const progressPercent = ref(0)
const progressMessage = ref('')
const progressColor = ref('#2563EB')
let _progressTimer: ReturnType<typeof setTimeout> | null = null

function showProgress(agent: string, percent: number, message: string) {
  if (_progressTimer) clearTimeout(_progressTimer)
  progressAgent.value = agentLabel(agent)
  progressPercent.value = Math.min(100, Math.max(0, percent))
  progressMessage.value = message
  progressColor.value = agentColor(agent)
  progressVisible.value = true
}

function hideProgress() {
  _progressTimer = setTimeout(() => {
    progressVisible.value = false
  }, 500)
}

function agentLabel(agent: string): string {
  const map: Record<string, string> = {
    supervisor: '学习助手',
    profile_agent: '画像采集',
    resource_agent: '资源生成',
    question_agent: '出题',
    path_agent: '路径规划',
    evaluation_agent: '学习评估',
  }
  return map[agent] || agent
}

function groupMessages(items: HistoryItem[]): ConvoGroup[] {
  const groups: ConvoGroup[] = []
  let i = 0
  while (i < items.length) {
    const user = items[i]
    if (user.role !== 'user') { i++; continue }
    const assistant = items[i + 1]
    const asstMsg = assistant && assistant.role === 'assistant' ? assistant.content : ''
    const asstAgent = assistant && assistant.role === 'assistant' ? assistant.agent_type : null
    // Clean title: strip common prefixes for better readability
    let title = user.content.replace(/^(教我|解释|什么是|帮我|给我|我想学|我要学|写一个|写一段|生成|请|麻烦|帮我|给我讲|讲一下)/, '').trim()
    if (title.length > 30) title = title.slice(0, 30) + '...'
    if (!title) title = user.content.slice(0, 30)
    const preview = title
    const dateLabel = dayjs(user.created_at).format('MM-DD HH:mm')
    groups.push({
      id: user.id,
      userMessage: user.content,
      assistantMessage: asstMsg,
      agentType: asstAgent,
      createdAt: user.created_at,
      dateLabel,
      preview,
    })
    i += asstMsg ? 2 : 1
  }
  return groups.reverse()
}

async function fetchHistory() {
  if (_fetchingHistory) return  // 防止并发
  _fetchingHistory = true
  historyLoading.value = true
  historyError.value = ''
  try {
    const res = await api.get<HistoryItem[]>('/chat/history', { params: { limit: 20 } })
    historyItems.value = res.data
    groupedHistory.value = groupMessages(res.data)
  } catch (e: unknown) {
    const err = e as { response?: { status?: number } }
    historyError.value = err.response?.status === 401 ? '请先登录' : '加载失败'
  } finally {
    historyLoading.value = false
    _fetchingHistory = false
  }
}

async function deleteConversation(convo: ConvoGroup) {
  // 删除对话组中的所有消息
  try {
    await ElMessageBox.confirm('确定删除这条对话记录吗？', '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch { return }
  try {
    for (const id of (convo.messageIds || [])) {
      await api.delete(`/chat/history/${id}`)
    }
    // 如果删除的是当前活跃对话，清空聊天
    if (convo.id === activeConvoId.value) {
      store.clearMessages()
      activeConvoId.value = null
    }
    ElMessage.success('已删除')
    await fetchHistory()
  } catch (e: unknown) {
    ElMessage.error('删除失败')
  }
}

async function clearAllHistory() {
  try {
    await ElMessageBox.confirm('确定清空全部对话历史吗？此操作不可恢复。', '清空全部对话', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch { return }
  try {
    // DELETE /api/chat/history → 清空当前用户所有对话历史
    const res = await api.delete<{ deleted: number }>('/chat/history')
    store.clearMessages()
    activeConvoId.value = null
    streamingId.value = ''
    historyItems.value = []
    groupedHistory.value = []
    ElMessage.success(`已清空 ${res.data?.deleted ?? 0} 条对话记录`)
  } catch {
    ElMessage.error('清空失败，请稍后重试')
  }
}

function agentColor(agentType: string | null): string {
  const map: Record<string, string> = {
    profile_agent: '#8B5CF6',
    resource_agent: '#10B981',
    question_agent: '#F59E0B',
    path_agent: '#3B82F6',
    evaluation_agent: '#2563EB',
  }
  return map[agentType || ''] || '#64748B'
}

function loadConversation(convo: ConvoGroup) {
  activeConvoId.value = convo.id
  store.clearMessages()
  store.addUserMessage(convo.userMessage)
  streamingId.value = store.messages[store.messages.length - 1].id
  if (convo.assistantMessage) {
    store.startAssistantReply()
    streamingId.value = store.messages[store.messages.length - 1].id
    store.appendToStreaming(convo.assistantMessage, convo.agentType || undefined)
    store.finishAssistantReply()
    streamingId.value = ''
  }
  sidebarOpen.value = false
  scroll()
}

function handleNewChat() {
  store.clearMessages()
  activeConvoId.value = null
  streamingId.value = ''
}

function quickAsk(text: string) {
  handleSend(text)
}

// Re-generate: remove last AI reply and re-send the user message that triggered it
function regenerate(_aiMsg: any, idx: number) {
  // Find the user message before this AI reply
  const msgs = store.messages
  let userMsg = ''
  for (let i = idx - 1; i >= 0; i--) {
    if (msgs[i].role === 'user') { userMsg = msgs[i].content; break }
  }
  if (!userMsg) return
  // Remove the AI reply
  store.messages.splice(idx, 1)
  // Re-send
  handleSend(userMsg)
}

// ── 图片类型（与 ChatInput ImageItem 对齐）──
interface ChatImage {
  url: string
  base64?: string
  name: string
  size: number
  type: string
}

function handleSend(content: string, images?: ChatImage[]) {
  if (store.isStreaming) return
  if (_sending) return  // 防抖：冷却期内不重复发送

  _sending = true
  setTimeout(() => { _sending = false }, SEND_COOLDOWN)

  // 将图片附加到用户消息（用于前端展示）
  const imageUrls = images?.map(img => img.url) || []
  store.addUserMessage(content, imageUrls.length > 0 ? imageUrls : undefined)
  scroll()
  store.startAssistantReply()
  streamingId.value = store.messages[store.messages.length - 1].id

  // 转换图片格式为 API 所需的 SendImage[]
  const apiImages: SendImage[] | undefined = images?.map(img => ({
    base64: img.base64 || '',
    mime_type: img.type,
    name: img.name,
  }))

  abortCtrl.value = sendMessageStream(
    content,
    (data: SSEChunk) => {
      // ── Progress event ──
      if (data.type === 'progress' && data.stage) {
        if (data.stage === 'generating') {
          showProgress(data.agent || 'resource_agent', data.progress || 0, data.content || data.message || '')
        } else if (data.stage === 'complete') {
          hideProgress()
        }
        return
      }

      // ── Agent 切换：更新当前 Agent 显示，不创建新消息 ──
      if (data.from && data.to) {
        store.setAgentSwitch(data.from, data.to)
        return
      }

      // ── 资源元数据：附加到当前流式消息 ──
      if (data.type === 'resource' && data.resource_type) {
        store.setResource(data.resource_type, data.resource_id || 0, data.title || '学习资源')
        return
      }

      // ── 智能建议推送：Agent分析完成后的下一步推荐 ──
      if (data.type === 'suggestion' && data.intent) {
        const routes: Record<string, string> = {
          evaluation: '/assessment', resource: '/chat', question: '/chat', path: '/chat', profile: '/profile'
        }
        const labels: Record<string, string> = {
          evaluation: '去做评估', resource: '去学习', question: '去练习', path: '去规划', profile: '完善画像'
        }
        ElNotification({
          title: '智能推荐',
          message: data.reason || '系统根据你的学习状态推荐下一步操作',
          type: 'info',
          duration: 5000,
          onClick: () => {
            const intent = data.intent || ''
            const to = routes[intent] || '/chat'
            if (intent !== 'profile') {
              router.push({ path: '/chat', query: { prompt: data.reason || '' } })
            } else {
              router.push(to)
            }
          },
        })
        return
      }

      // ── 普通文本内容：追加到当前流式消息 ──
      const text = data.content || ''
      if (text) {
        store.appendToStreaming(text, data.agent)
      }
      scroll()
    },
    () => {
      store.finishAssistantReply()
      streamingId.value = ''
      abortCtrl.value = null
      hideProgress()
      scroll()
      fetchHistory()
    },
    (err) => {
      if (err.name !== 'AbortError') {
        store.appendToStreaming(`\n\n> 回复生成中断，请稍后重试`)
      }
      store.finishAssistantReply()
      streamingId.value = ''
      abortCtrl.value = null
      hideProgress()
    },
    apiImages,  // 多模态：传递图片列表
  )
}

const showScrollBtn = ref(false)

function scroll() {
  nextTick(() => {
    if (listRef.value) {
      listRef.value.scrollTop = listRef.value.scrollHeight
      showScrollBtn.value = false
    }
  })
}

function scrollToBottom() {
  if (listRef.value) {
    listRef.value.scrollTo({ top: listRef.value.scrollHeight, behavior: 'smooth' })
  }
}

function onScroll() {
  if (!listRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = listRef.value
  showScrollBtn.value = scrollHeight - scrollTop - clientHeight > 120
}

const route = useRoute()
const router = useRouter()

onMounted(() => {
  fetchHistory()
  // 处理从 AgentCenter 关键词点击过来的预设提示词
  const prompt = route.query.prompt as string
  if (prompt) {
    // 延迟发送，等页面渲染完成
    setTimeout(() => handleSend(prompt), 300)
    // 清除 URL 参数避免刷新重复发送
    router.replace({ path: '/chat', query: {} })
  }
})
</script>

<style scoped>
/* ═══════════════════════════════════════════════
   A3 Chat — Clean Professional Design
   Blue-white theme · Minimal animations
   ═══════════════════════════════════════════════ */

/* ── Main Layout ── */
.chat-layout {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-page);
  overflow: hidden;
}

/* ── Drawer ── */
.drawer-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--bg-card);
}
.drawer-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
.drawer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.new-chat-btn {
  border-radius: var(--radius-md) !important;
  font-weight: 600 !important;
  background: var(--primary) !important;
  border: none !important;
}

.history-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.history-item {
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background .2s, border-color .2s;
  border: 1px solid transparent;
}
.history-item:hover {
  background: rgba(37,99,235,.04);
  border-color: rgba(37,99,235,.1);
}
.history-item.active {
  background: rgba(37,99,235,.06);
  border-color: rgba(37,99,235,.15);
}
.hi-header { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
.hi-date { font-size: 12px; color: var(--text-muted); font-weight: 500; }
.hi-agent { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; }
.hi-text { font-size: 13px; color: var(--text-secondary); line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.sb-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 0;
  color: var(--text-muted);
  font-size: 13px;
}
.sb-state.error { color: var(--red); }
.sb-empty-text { font-size: 13px; color: var(--text-muted); }
.spinner { animation: spin 1s linear infinite; }

/* ═══ Topbar ═══ */
.chat-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 24px;
  flex-shrink: 0;
  background: rgba(255,255,255,.7);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 5;
  border-bottom: 1px solid var(--border);
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.stop-btn {
  border-radius: 999px !important;
  font-size: 12px !important;
  font-weight: 600 !important;
}
.history-toggle-btn {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  gap: 5px;
  padding: 7px 16px;
  border-radius: 999px;
  transition: all .2s;
  background: rgba(255,255,255,.6);
  border: 1px solid var(--border);
}
.history-toggle-btn:hover {
  color: var(--primary);
  background: #fff;
  border-color: rgba(37,99,235,.18);
}
.topbar-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--green);
  font-weight: 600;
}
.status-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--green);
  transition: background 0.3s;
}
.status-dot.generating {
  background: #10B981;
  animation: pulse-dot 1s ease-in-out infinite;
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.status-text {
  font-size: 12px;
  color: inherit;
  transition: color 0.3s;
}

/* ═══ Progress Bar ═══ */
.progress-bar-wrap {
  flex-shrink: 0;
  padding: 10px 24px 8px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}
.progress-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.progress-agent {
  font-size: 12px;
  font-weight: 700;
  color: var(--primary);
}
.progress-msg {
  font-size: 11px;
  color: var(--text-muted);
}
.progress-bar :deep(.el-progress-bar__outer) {
  background: var(--bg-muted);
  border-radius: 2px;
}
.progress-bar :deep(.el-progress__text) {
  font-size: 11px !important;
  font-weight: 600 !important;
}
.progress-fade-enter-active { transition: all 0.3s ease; }
.progress-fade-leave-active { transition: all 0.3s ease; }
.progress-fade-enter-from,
.progress-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* ═══ Messages Area ═══ */
.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 24px 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  position: relative;
  scroll-behavior: smooth;
  z-index: 1;
}

/* ═══ Empty State — Enhanced Welcome ═══ */
.empty {
  text-align: center;
  padding: 50px 20px 60px;
  color: var(--text-secondary);
}
.empty-icon {
  width: 80px; height: 80px;
  border-radius: 50%;
  background: var(--primary-light);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 20px;
  border: 1px solid rgba(37,99,235,.1);
}
.empty h3 {
  font-size: 22px;
  margin-bottom: 6px;
  font-weight: 700;
  color: var(--text-primary);
}
.empty p {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 24px;
}

.empty-features {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  max-width: 500px;
  margin: 0 auto 28px;
  text-align: left;
}
.feature-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 13px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  transition: all 0.2s;
}
.feature-item:hover {
  border-color: rgba(37,99,235,.2);
  box-shadow: var(--shadow-xs);
}
.feature-item .el-icon {
  margin-top: 2px;
  flex-shrink: 0;
  color: var(--primary);
}
.feature-item div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.feature-item strong {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
}
.feature-item span {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
}

.empty-suggestions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  max-width: 520px;
  margin: 0 auto;
}
.suggestion-tag {
  padding: 9px 16px;
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  border: 1px solid var(--border);
  font-size: var(--font-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all .2s;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}
.suggestion-tag:hover {
  border-color: var(--primary);
  color: var(--primary);
}

/* ═══ Scroll to Bottom Button ═══ */
.scroll-bottom-btn {
  position: absolute;
  bottom: 16px;
  right: 20px;
  z-index: 10;
  width: 36px; height: 36px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .2s;
}
.scroll-bottom-btn:hover {
  color: #fff;
  background: var(--primary);
  border-color: var(--primary);
}
.scroll-fade-enter-active,
.scroll-fade-leave-active {
  transition: opacity .2s, transform .2s;
}
.scroll-fade-enter-from,
.scroll-fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

/* ═══ Message Entry Animation ═══ */
.msg-enter {
  animation: msgSlideIn 0.3s ease both;
}
@keyframes msgSlideIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.msg-streaming .bb {
  border-color: rgba(59,130,246,.25);
}

/* ═══ Responsive ═══ */
@media (max-width: 768px) {
  .empty-features {
    grid-template-columns: 1fr;
    max-width: 320px;
  }
  .chat-topbar {
    padding: 8px 14px;
  }
  .messages {
    padding: 14px 14px 6px;
  }
  .progress-bar-wrap {
    padding: 8px 14px 6px;
  }
}
</style>
