/*
资源导出 API

封装 notebook 下载和 TTS 音频获取请求
*/
import api from './index'

export function getNotebookUrl(resourceId: number): string {
  return `/api/resources/${resourceId}/export/notebook`
}

export function getAudioUrl(resourceId: number): string {
  return `/api/resources/${resourceId}/audio`
}

export async function downloadNotebook(resourceId: number, title: string): Promise<void> {
  const token = localStorage.getItem('token')
  const res = await fetch(getNotebookUrl(resourceId), {
    headers: token ? { Authorization: 'Bearer ' + token } : {},
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '下载失败' }))
    throw new Error(err.detail || '下载失败')
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = (title || 'notebook').replace(/\s+/g, '_') + '.ipynb'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
