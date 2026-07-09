/*
TTS 语音合成 API 封装

后端: POST /api/tts/synthesize  → 返回 MP3 音频字节 (audio/mpeg)
用法:
  const url = await synthesizeSpeech('要朗读的文本')
  new Audio(url).play()
*/
import api from './index'

export async function synthesizeSpeech(text: string, voice = 'xiaoyan'): Promise<string> {
  const resp = await api.post(
    '/tts/synthesize',
    { text: text.slice(0, 500), voice },
    { responseType: 'arraybuffer' },
  )
  const blob = new Blob([resp.data], { type: 'audio/mpeg' })
  return URL.createObjectURL(blob)
}
