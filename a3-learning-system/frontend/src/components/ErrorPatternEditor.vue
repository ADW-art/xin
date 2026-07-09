<template>
  <!-- 易错模式可视化编辑器 (业内最佳实践: Notion/Anki chip + 表单) -->
  <div class="error-pattern-editor">
    <!-- 列表 -->
    <div v-for="(item, idx) in patterns" :key="idx" class="ep-row">
      <el-select
        v-model="item.type"
        size="small"
        placeholder="选择类型"
        class="ep-type"
        @change="syncModel"
      >
        <el-option
          v-for="opt in typeOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>

      <div class="ep-concepts">
        <el-tag
          v-for="(c, ci) in item.concepts"
          :key="ci"
          closable
          size="small"
          type="danger"
          effect="light"
          class="ep-chip"
          @close="removeConcept(idx, ci)"
        >
          {{ c }}
        </el-tag>
        <el-input
          v-model="conceptInputs[idx]"
          size="small"
          placeholder="输入知识点后回车"
          class="ep-input"
          @keydown.enter.prevent="addConcept(idx)"
          @blur="addConcept(idx)"
        />
      </div>

      <el-button
        text
        size="small"
        type="danger"
        class="ep-del"
        @click="removePattern(idx)"
      >
        <el-icon><Delete /></el-icon>
      </el-button>
    </div>

    <!-- 添加按钮 -->
    <el-button
      size="small"
      type="primary"
      plain
      class="ep-add"
      @click="addPattern"
    >
      <el-icon><Plus /></el-icon>
      添加易错模式
    </el-button>

    <!-- 操作 -->
    <div class="ep-actions">
      <el-button size="small" @click="cancel">取消</el-button>
      <el-button size="small" type="primary" @click="save">保存</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'

interface ErrorPattern {
  type: string
  concepts: string[]
}

const props = defineProps<{
  modelValue: string
  fieldName: string  // 告诉父组件这个编辑器对应哪个字段
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'save'): void
  (e: 'change'): void  // auto-save 触发, 父组件用 props.fieldName 识别字段
}>()

// 5 个固定的错误类型 (业内最佳实践: 限定选项, 避免用户瞎填)
const typeOptions = [
  { value: 'confusion',       label: '概念混淆' },
  { value: 'forgetting',      label: '知识点遗忘' },
  { value: 'carelessness',    label: '粗心大意' },
  { value: 'misunderstanding', label: '理解偏差' },
  { value: 'application',     label: '应用困难' },
]

const patterns = ref<ErrorPattern[]>([])
const conceptInputs = ref<string[]>([])
const original = ref<string>('')

function parseInput() {
  if (!props.modelValue) {
    patterns.value = []
    conceptInputs.value = []
    return
  }
  try {
    const parsed = JSON.parse(props.modelValue)
    if (Array.isArray(parsed)) {
      patterns.value = parsed.map(p => ({
        type: p.type || 'confusion',
        concepts: Array.isArray(p.concepts) ? [...p.concepts] : [],
      }))
    } else {
      patterns.value = []
    }
  } catch {
    patterns.value = []
  }
  conceptInputs.value = patterns.value.map(() => '')
  original.value = props.modelValue
}

function syncModel() {
  // 清理空 concept 的项
  const cleaned = patterns.value
    .filter(p => p.concepts && p.concepts.length > 0)
    .map(p => ({ type: p.type, concepts: [...p.concepts] }))
  emit('update:modelValue', JSON.stringify(cleaned))
  emit('change')  // 通知父组件触发 auto-save
}

function addPattern() {
  patterns.value.push({ type: 'confusion', concepts: [] })
  conceptInputs.value.push('')
  syncModel()
}

function removePattern(idx: number) {
  patterns.value.splice(idx, 1)
  conceptInputs.value.splice(idx, 1)
  syncModel()
}

function addConcept(idx: number) {
  const txt = (conceptInputs.value[idx] || '').trim()
  console.log('[ErrorPatternEditor] addConcept called, idx=', idx, 'txt=', JSON.stringify(txt), 'patterns[idx].concepts=', patterns.value[idx]?.concepts)
  if (!txt) {
    console.log('[ErrorPatternEditor] txt empty, return')
    return
  }
  if (!patterns.value[idx].concepts.includes(txt)) {
    patterns.value[idx].concepts.push(txt)
    conceptInputs.value[idx] = ''
    syncModel()
    console.log('[ErrorPatternEditor] chip added, new list:', patterns.value[idx].concepts)
  } else {
    conceptInputs.value[idx] = ''
    console.log('[ErrorPatternEditor] duplicate, skipped')
  }
}

function removeConcept(idx: number, ci: number) {
  patterns.value[idx].concepts.splice(ci, 1)
  syncModel()
}

function save() {
  // 去除 concept 为空的项
  const cleaned = patterns.value
    .filter(p => p.concepts && p.concepts.length > 0)
    .map(p => ({ type: p.type, concepts: [...p.concepts] }))
  emit('update:modelValue', JSON.stringify(cleaned))
  emit('save')
}

function cancel() {
  // 关键: 还原 editForm 到原始值, 触发 update:modelValue 但不触发 change
  // 这样 auto-save 不会把"取消"误判为"保存空值"
  emit('update:modelValue', original.value)
  parseInput()
  // 注意: 不 emit('change'), 让父组件区分"用户改动了"vs"用户取消了"
}

watch(() => props.modelValue, parseInput)
onMounted(parseInput)
</script>

<style scoped>
.error-pattern-editor { display: flex; flex-direction: column; gap: 8px; }

.ep-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px;
  background: rgba(239, 68, 68, 0.04);
  border: 1px solid rgba(239, 68, 68, 0.15);
  border-radius: 6px;
}

.ep-type { width: 110px; flex-shrink: 0; }

.ep-concepts {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  min-height: 28px;
}

.ep-chip { font-size: 11px; }

.ep-input {
  flex: 1;
  min-width: 80px;
  --el-input-width: 100%;
}
.ep-input :deep(.el-input__wrapper) { padding: 0 6px; }

.ep-del { flex-shrink: 0; }

.ep-add {
  align-self: flex-start;
  width: 100%;
  border-style: dashed;
}

.ep-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #EBEEF3;
}
</style>
