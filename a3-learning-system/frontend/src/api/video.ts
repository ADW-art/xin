/*
Video API 模块

作用：
  封装视频生成相关的后端接口调用

关联文件：
  components/chat/ChatMessage.vue
*/
import api from './index'

export function generateVideo(resourceId: number) {
  return api.post('/video/generate', { resource_id: resourceId })
}

export function getVideoStatus(taskId: string) {
  return api.get(`/video/status/${taskId}`)
}
