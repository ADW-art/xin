/*
SSE 流式对话 API

作用：
  封装后端 SSE（Server-Sent Events）流式接口 POST /api/chat/send
  通过 Fetch API 逐行读取流式响应，按事件类型分发数据

关联文件：
  stores/chat.ts  ← 调用本函数，将收到的数据更新到 Pinia 状态
  api/index.ts    ← 拦截器配置参考（本文件直接使用 fetch，不通过 axios）

使用方式：
  const ctrl = sendMessageStream(
    "你好",
    (data) => { console.log(data) },
    () => {},
    (err) => { console.error(err) }
  )
  ctrl.abort()
*/
import api from './index'

// SSE 推送的数据块类型——与后端 sender.py 约定的格式一致
export interface SSEChunk {
  type?: string        // 数据类型（预留）
  content?: string     // 文本内容
  agent?: string       // 当前 Agent 名称
  status?: string      // 状态（如 "complete"）
  from?: string        // Agent 切换来源
  to?: string          // Agent 切换目标
  message?: string     // 错误消息
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
*/
export function sendMessageStream(
  message: string,
  onChunk: (data: SSEChunk) => void,
  onDone: () => void,
  onError: (err: Error) => void
): AbortController {
  const controller = new AbortController()

  // 使用原生 fetch 而非 axios，因为 axios 对流式响应支持不完善
  fetch('/api/chat/send', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('token')}`,  // 从 localStorage 取 JWT
    },
    body: JSON.stringify({ content: message }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error('请求失败')
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
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (currentEvent === 'done') {
                onDone()
                return
              }
              if (currentEvent === 'error') {
                onError(new Error(data.message || '未知错误'))
                return
              }
              onChunk(data)
            } catch {
              // JSON 解析失败，跳过该行
            }
          }
        }
      }
      onDone()
    })
    .catch(onError)

  return controller
}
