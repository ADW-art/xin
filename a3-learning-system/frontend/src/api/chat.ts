import api from './index'

// SSE流式对话（核心接口）
export function sendMessageStream(
  message: string,
  onChunk: (data: any) => void,
  onDone: () => void,
  onError: (err: Error) => void
): AbortController {
  const controller = new AbortController()

  fetch('/api/chat/send', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('token')}`,
    },
    body: JSON.stringify({ content: message }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error('请求失败')
      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              onChunk(data)
              if (data.type === 'done') {
                onDone()
                return
              }
            } catch {}
          }
        }
      }
      onDone()
    })
    .catch(onError)

  return controller
}
