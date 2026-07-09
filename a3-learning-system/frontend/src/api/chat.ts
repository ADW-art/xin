/*
SSE 流式对话 API

作用：
  封装后端 SSE（Server-Sent Events）流式接口 POST /api/chat/send
  通过 Fetch API 逐行读取流式响应，按事件类型分发数据

关联文件：
  stores/chat.ts  ← 调用本函数，将收到的数据更新到 Pinia 状态
  api/index.ts    ← 拦截器配置参考（本文件直接使用 fetch，不通过 axios）

使用方式：
  const ctrl = sendMessageStream("你好", onChunk, onDone, onError)
  ctrl.abort()
*/
import api from './index'

// SSE 推送的数据块类型——与后端 sender.py 约定的格式一致
export interface SSEChunk {
  type?: string        // 数据类型："text" | "resource" | "agent_switch" | "progress"
  content?: string     // 文本内容（type=text 时）
  agent?: string       // 当前 Agent 名称
  status?: string      // 状态（如 "complete"）
  from?: string        // Agent 切换来源
  to?: string          // Agent 切换目标
  message?: string     // 错误消息
  // 资源事件字段（type=resource 时）
  resource_type?: string   // mindmap / code_example / document / question_set / video_script
  resource_id?: number     // 资源ID
  title?: string           // 资源标题
  // 进度事件字段（type=progress 时）
  stage?: string       // "generating" | "complete"
  progress?: number    // 0-100 进度百分比
  // 智能建议字段（type=suggestion 时）
  intent?: string      // evaluation / resource / question / path
  reason?: string      // 建议原因描述
  // 多Agent协同事件字段（type=collaboration 时）
  mode?: string        // "qa_parallel" | "resource_parallel" | "path_parallel"
  // 学习路径更新事件字段（type=path_update 时）
  action?: string      // "replanned"
  new_unlocked?: string[]  // 新解锁的知识点
  skipped?: string[]       // 因已掌握而跳过的知识点
  current_node?: string    // 当前推荐节点
  current_index?: number   // 当前节点序号
  total_nodes?: number     // 路径总节点数
  // 复习提醒事件字段（type=review_due 时）— P1-24
  total?: number           // 到期复习知识点总数
  high_risk?: number       // 高风险数量
  items?: Array<{ concept: string; retention: number; risk: string; next_review: string | null; review_count: number; interval_days: number }>
}

/*
发送消息并接收 SSE 流式响应

参数说明：
  message   用户输入的消息文本
  onChunk   收到数据块时的回调（每段内容都会触发）
  onDone    全部接收完成时的回调（收到 event: done）
  onError   请求失败或收到错误事件时的回调

返回值：
  AbortController 可用于手动中断请求（如用户点击停止）

SSE 事件类型（与后端约定）：
  agent_switch  → { from, to }          Agent 切换
  message       → { content, agent }     流式文本片段
  resource      → { type, resource_type, title } 资源元数据
  done          → { status }             完成
  error         → { message, detail? }   错误
*/
export interface SendImage {
  base64: string       // 纯 base64 数据（不含 data:image/xxx;base64, 前缀）
  mime_type: string    // 如 "image/png", "image/jpeg"
  name: string         // 文件名
}

export function sendMessageStream(
  message: string,
  onChunk: (data: SSEChunk) => void,
  onDone: () => void,
  onError: (err: Error) => void,
  images?: SendImage[],   // 多模态：可选图片列表
): AbortController {
  const controller = new AbortController()

  // 构建请求体：支持纯文本 / 文本+图片 多模态
  const body: Record<string, any> = { content: message }
  if (images && images.length > 0) {
    body.images = images.map(img => ({
      base64: img.base64,
      mime_type: img.mime_type,
      name: img.name,
    }))
  }

  fetch('/api/chat/send', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('token')}`,  // 从 localStorage 取 JWT
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(`请求失败 (${response.status})`)
      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed) continue  // 跳过空行

          if (trimmed.startsWith('event: ')) {
            currentEvent = trimmed.slice(7).trim()
          } else if (trimmed.startsWith('data: ')) {
            try {
              const data = JSON.parse(trimmed.slice(6))

              if (currentEvent === 'done') {
                onDone()
                return
              }
              if (currentEvent === 'error') {
                onError(new Error(data.message || data.detail || '未知错误'))
                return
              }
              // 显式标注事件类型，方便前端区分处理
              data.type = currentEvent
              // 过滤空 content（后端可能发送空 chunk）
              if (data.content === undefined || data.content !== '') {
                onChunk(data)
              }
            } catch {
              // JSON 解析失败，跳过该行（可能是 [DONE] 等非 JSON 数据）
            }
          }
        }
      }
      // 流正常结束（reader done），触发 onDone
      onDone()
    })
    .catch((err: Error) => {
      // AbortError 是用户主动取消，不算错误
      if (err.name !== 'AbortError') {
        onError(err)
      }
    })

  return controller
}
