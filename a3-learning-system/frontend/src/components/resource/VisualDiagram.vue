<!--
VisualDiagram.vue — AI 知识图解组件

解析 visual_diagram 资源中的 [IMAGE_PROMPT]...[EXPLANATION] 对,
调用后端星火图像生成 API, 将文本描述转为实际配图展示.
-->
<template>
  <div class="vd-container">
    <div class="vd-toolbar" v-if="sections.length > 0">
      <span class="vd-count">{{ sections.length }} 张图解</span>
      <el-button
        type="primary"
        size="small"
        :loading="generating"
        @click="generateAll"
        :disabled="allGenerated"
      >
        <el-icon :size="14"><PictureFilled /></el-icon>
        {{ allGenerated ? '已全部生成' : generating ? '生成中...' : 'AI 生成配图' }}
      </el-button>
    </div>

    <div v-if="sections.length === 0" class="vd-empty">
      <p>暂无图解内容</p>
    </div>

    <div v-else class="vd-sections">
      <div v-for="(sec, i) in sections" :key="i" class="vd-section">
        <div class="vd-image-area">
          <div v-if="sec.imageUrl" class="vd-image-wrapper">
            <img :src="sec.imageUrl" :alt="'图解 ' + (i + 1)" class="vd-image" />
          </div>
          <div v-else-if="sec.generating" class="vd-placeholder generating">
            <el-icon class="spin" :size="28"><Loading /></el-icon>
            <span>AI 正在生成配图...</span>
          </div>
          <div v-else-if="sec.error" class="vd-placeholder error">
            <span>{{ sec.error }}</span>
          </div>
          <div v-else class="vd-placeholder">
            <span>点击上方按钮生成配图</span>
          </div>
        </div>
        <div class="vd-explanation" v-if="sec.explanation">
          <div class="vd-explain-label">说明</div>
          <div class="vd-explain-text">{{ sec.explanation }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { PictureFilled, Loading } from '@element-plus/icons-vue'
import api from '@/api/index'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  content: string
  resourceId: number
}>()

interface Section {
  prompt: string
  explanation: string
  imageUrl: string | null
  generating: boolean
  error: string | null
}

const sections = ref<Section[]>([])
const generating = ref(false)

function parseContent(content: string): Section[] {
  const result: Section[] = []
  const promptRegex = /\[IMAGE_PROMPT\]\s*\n?([\s\S]*?)\[\/IMAGE_PROMPT\]/g
  const explainRegex = /\[EXPLANATION\]\s*\n?([\s\S]*?)(?=\[IMAGE_PROMPT\]|$)/g

  let promptMatch: RegExpExecArray | null
  const prompts: string[] = []
  while ((promptMatch = promptRegex.exec(content)) !== null) {
    prompts.push(promptMatch[1].trim())
  }

  const explanations: string[] = []
  let explainMatch: RegExpExecArray | null
  while ((explainMatch = explainRegex.exec(content)) !== null) {
    explanations.push(explainMatch[1].trim())
  }

  const count = Math.max(prompts.length, explanations.length)
  for (let i = 0; i < count; i++) {
    result.push({
      prompt: prompts[i] || '',
      explanation: explanations[i] || '',
      imageUrl: null,
      generating: false,
      error: null,
    })
  }
  return result
}

const allGenerated = computed(() =>
  sections.value.length > 0 && sections.value.every(s => s.imageUrl !== null)
)

watch(() => props.content, (val) => {
  sections.value = parseContent(val || '')
}, { immediate: true })

async function generateAll() {
  if (generating.value) return
  generating.value = true

  try {
    const token = localStorage.getItem('token')
    const resp = await api.post(
      `/resources/${props.resourceId}/generate-images`,
      {},
      { headers: token ? { Authorization: 'Bearer ' + token } : {} }
    )
    const data = (resp as any).data
    const images = data.images || []

    for (const img of images) {
      if (img.status === 'success' && sections.value[img.index]) {
        sections.value[img.index].imageUrl = img.url
        sections.value[img.index].generating = false
        sections.value[img.index].error = null
      } else if (sections.value[img.index]) {
        sections.value[img.index].error = img.status || '生成失败'
      }
    }

    if (data.generated > 0) {
      ElMessage.success(`已生成 ${data.generated} 张配图`)
    } else {
      ElMessage.warning(data.message || '无配图生成')
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '配图生成失败')
  } finally {
    generating.value = false
  }
}
</script>

<style scoped>
.vd-container {
  width: 100%;
}
.vd-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border);
}
.vd-count {
  font-size: var(--font-sm);
  color: var(--text-secondary);
  font-weight: 500;
}
.vd-sections {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.vd-section {
  display: flex;
  gap: 20px;
  padding: 16px;
  background: var(--bg-page);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
@media (max-width: 768px) {
  .vd-section {
    flex-direction: column;
  }
}
.vd-image-area {
  flex: 0 0 320px;
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.vd-image-wrapper {
  width: 100%;
}
.vd-image {
  width: 100%;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
}
.vd-placeholder {
  width: 100%;
  height: 200px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: rgba(59,130,246,.04);
  border: 2px dashed var(--border);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  font-size: var(--font-sm);
}
.vd-placeholder.generating {
  border-color: var(--primary);
  color: var(--primary);
  background: rgba(59,130,246,.06);
}
.vd-placeholder.error {
  border-color: #DC2626;
  color: #DC2626;
  background: rgba(220,38,38,.04);
}
.vd-explanation {
  flex: 1;
  min-width: 0;
}
.vd-explain-label {
  font-size: var(--font-xs);
  font-weight: 600;
  color: var(--primary);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: .5px;
}
.vd-explain-text {
  font-size: var(--font-sm);
  line-height: 1.7;
  color: var(--text-primary);
}
.vd-empty {
  text-align: center;
  padding: 40px;
  color: var(--text-muted);
}
.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg) }
  to { transform: rotate(360deg) }
}
</style>
