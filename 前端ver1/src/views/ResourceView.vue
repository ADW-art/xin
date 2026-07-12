<template>
  <div class="page">
    <div class="hero a-slide">
      <h1>资源库</h1>
      <p>AI 为你生成的个性化学习资源</p>
    </div>

    <!-- Search bar -->
    <div class="resource-search">
      <el-input v-model="searchQuery" placeholder="搜索资源标题或内容..." clearable size="large" @input="onSearchInput">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="loading-state">
      <div v-for="i in 4" :key="i" class="skel-card">
        <el-skeleton animated>
          <template #template>
            <div class="skel-inner">
              <el-skeleton-item variant="rect" class="skel-icon" />
              <div class="skel-body">
                <el-skeleton-item variant="text" style="width: 30%; margin-bottom: 6px;" />
                <el-skeleton-item variant="text" style="width: 70%; margin-bottom: 4px;" />
                <el-skeleton-item variant="text" style="width: 50%;" />
              </div>
            </div>
          </template>
        </el-skeleton>
      </div>
    </div>

    <!-- Error state -->
    <div v-else-if="loadError" class="error-state a-scale">
      <el-icon :size="40"><WarningFilled /></el-icon>
      <h3>加载失败</h3>
      <p>{{ loadError }}</p>
      <el-button type="primary" @click="loadResources">重新加载</el-button>
    </div>

    <!-- Empty state -->
    <div v-else-if="items.length===0" class="empty a-scale">
      <svg viewBox="0 0 200 120" class="e-svg">
        <rect x="40" y="15" width="50" height="8" rx="4" fill="rgba(37,99,235,.18)"/>
        <rect x="44" y="27" width="35" height="3" rx="1.5" fill="rgba(37,99,235,.10)"/>
        <rect x="95" y="10" width="65" height="14" rx="4" fill="rgba(37,99,235,.06)" stroke="rgba(37,99,235,.15)" stroke-width="1"/>
        <rect x="100" y="28" width="45" height="3" rx="1.5" fill="rgba(255,255,255,.05)"/>
        <circle cx="150" cy="60" r="28" fill="rgba(139,92,246,.06)" stroke="rgba(139,92,246,.15)" stroke-width="1.5"/>
        <circle cx="150" cy="60" r="12" fill="rgba(139,92,246,.10)"/>
        <path d="M108 52l30-10" stroke="rgba(37,99,235,.10)" stroke-width="1.5" stroke-dasharray="4 3"/>
      </svg>
      <h3>暂无资源</h3>
      <p>去对话中让 AI 为你生成学习资料</p>
      <el-button type="primary" @click="$router.push('/chat')">前往对话</el-button>
    </div>

    <!-- Resource grid -->
    <div v-else class="grid">
      <div
        v-for="(r,i) in items"
        :key="r.id"
        class="r-card"
        :style="`animation:fadeUp .45s ease both;animation-delay:${i*80}ms`"
        @click="router.push('/resources/'+r.id)"
      >
        <!-- 左侧图标区 -->
        <div class="r-icon-wrap">
          <div class="r-icon" :style="{ background: r.color + '14', color: r.color }">
            <el-icon :size="20"><component :is="typeIcon(r.resource_type)" /></el-icon>
          </div>
        </div>

        <!-- 右侧内容区 -->
        <div class="r-body">
          <div class="r-header">
            <span class="r-type" :style="{ color: r.color }">{{ typeLabel(r.resource_type) }}</span>
            <span v-if="r.difficulty_level" class="r-tag">
              {{ difficultyLabel(r.difficulty_level) }}
            </span>
          </div>
          <div class="r-title">{{ r.title }}</div>
          <div class="r-meta">{{ r.knowledge_points?.join(' · ') || '暂无关联知识点' }}</div>
        </div>

        <!-- 删除 + 箭头 -->
        <button class="r-del" title="删除资源" @click.stop="onDelete(r)">
          <el-icon><Delete /></el-icon>
        </button>
        <div class="r-arrow">
          <el-icon><ArrowRight /></el-icon>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, WarningFilled, Delete, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteResource, type ResourceItem } from '@/api/resource'
import api from '@/api/index'

interface ResourceDisplayItem extends ResourceItem { color: string }

const loading = ref(true)
const loadError = ref('')
const items = ref<ResourceDisplayItem[]>([])
const searchQuery = ref('')
let _searchTimer: ReturnType<typeof setTimeout> | null = null

function onSearchInput() {
  if (_searchTimer) clearTimeout(_searchTimer)
  _searchTimer = setTimeout(() => loadResources(), 300)
}
// 蓝白主色调 + 协调的辅助色
const colors = ['#2563EB', '#3B82F6', '#60A5FA', '#1D4ED8', '#0EA5E9', '#6366F1']
const router = useRouter()

const typeIcons: Record<string, string> = {
  document: 'Document',
  mindmap: 'DataBoard',
  question_set: 'EditPen',
  video_script: 'VideoPlay',
  code_example: 'Monitor',
}
const typeLabels: Record<string, string> = {
  document: '知识文档',
  mindmap: '思维导图',
  question_set: '练习题集',
  video_script: '讲解脚本',
  code_example: '代码案例',
}

function typeIcon(type?: string): string {
  return typeIcons[type || ''] || 'Document'
}

function typeLabel(type?: string): string {
  return typeLabels[type || ''] || '学习资源'
}

function difficultyLabel(level: number): string {
  const map: Record<number, string> = {
    1: '入门',
    2: '基础',
    3: '中等',
    4: '进阶',
    5: '困难',
  }
  return map[level] || `Lv.${level}`
}

async function loadResources() {
  loading.value = true
  loadError.value = ''
  try {
    const params: Record<string, any> = { size: 50 }
    if (searchQuery.value) params.keyword = searchQuery.value
    const res = await api.get('/resources', { params })
    items.value = (res.data || []).map((r: ResourceItem, i: number) => ({
      ...r,
      color: colors[i % 6],
    }))
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    loadError.value = err?.response?.data?.detail || err.message || '网络错误，请检查连接'
  } finally {
    loading.value = false
  }
}

onMounted(loadResources)

// 删除资源（真实调用 DELETE /api/resources/{id}）
async function onDelete(r: ResourceDisplayItem) {
  try {
    await ElMessageBox.confirm(`确定删除「${r.title}」吗？`, '删除资源', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return // 用户取消
  }
  try {
    await deleteResource(r.id)
    items.value = items.value.filter((x) => x.id !== r.id)
    ElMessage.success('已删除')
  } catch {
    ElMessage.error('删除失败')
  }
}
</script>

<style scoped>
/* ═══ 页面容器 ═══ */
.page {
  max-width: 1040px;
  margin: 0 auto;
  padding: 32px 28px 56px;
}

/* ═══ Hero 标题区 ═══ */
.hero { margin-bottom: 32px; }
.hero h1 {
  font-size: var(--font-3xl);
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.5px;
}
.hero p {
  font-size: var(--font-base);
  color: var(--text-secondary);
  margin-top: 6px;
}

/* ═══ Loading Skeleton ═══ */
.loading-state {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.skel-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: 16px 20px;
}
.skel-inner {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
}
.skel-icon {
  width: 48px !important;
  height: 48px !important;
  border-radius: var(--radius-md) !important;
  flex-shrink: 0;
}
.skel-body {
  flex: 1;
  min-width: 0;
}

/* ═══ Error State ═══ */
.error-state {
  text-align: center;
  padding: 64px 0;
}
.error-state .el-icon {
  color: var(--red, #EF4444);
  margin-bottom: 16px;
}
.error-state h3 {
  font-size: var(--font-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}
.error-state p {
  font-size: var(--font-sm);
  color: var(--text-muted);
  margin-bottom: 20px;
  max-width: 360px;
  margin-left: auto;
  margin-right: auto;
}

/* ═══ 加载 & 空状态 ═══ */
.loading {
  display: flex;
  justify-content: center;
  padding: 80px 0;
  color: var(--text-muted);
}
.spin { animation: spin 1s linear infinite; }

.empty {
  text-align: center;
  padding: 64px 0;
}
.e-svg {
  width: 200px;
  height: 120px;
  margin-bottom: 20px;
  opacity: 0.55;
}
.empty h3 {
  font-size: var(--font-xl);
  font-weight: 700;
  color: var(--text-primary);
}
.empty p {
  font-size: var(--font-sm);
  color: var(--text-muted);
  margin: 6px 0 20px;
}

/* ═══ 卡片网格 ═══ */
.grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

/* ═══ 单张资源卡片 — 蓝白简洁风格 ═══ */
.r-card {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: 22px 24px;
  display: flex;
  align-items: center;
  gap: 18px;
  cursor: pointer;
  transition: all 0.25s ease;
  overflow: hidden;
}

.r-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--primary);
  opacity: 0;
  transition: opacity 0.25s ease;
}

.r-card:hover {
  border-color: rgba(37,99,235,0.35);
}

.r-card:hover::before {
  opacity: 1;
}

/* ── 左侧图标区 ── */
.r-icon-wrap {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.r-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s ease;
}

.r-card:hover .r-icon {
  transform: scale(1.06);
}

/* ── 中间内容区 ── */
.r-body {
  flex: 1;
  min-width: 0; /* 防止文字溢出flex容器 */
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.r-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.r-type {
  font-size: var(--font-xs);
  font-weight: 600;
  letter-spacing: 0.3px;
  white-space: nowrap;
}

.r-tag {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  background: var(--bg-muted);
  padding: 2px 8px;
  border-radius: 999px;
  white-space: nowrap;
}

.r-title {
  font-size: var(--font-base);
  font-weight: 650;
  color: var(--text-primary);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.r-meta {
  font-size: var(--font-xs);
  color: var(--text-muted);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 右侧箭头 ── */
.r-arrow {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 14px;
  transition: all 0.25s ease;
  opacity: 0;
  transform: translateX(-4px);
}

/* ── 删除按钮（hover 显示） ── */
.r-del {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: all 0.2s ease;
}
.r-card:hover .r-del { opacity: 1; }
.r-del:hover { color: #EF4444; border-color: #EF4444; background: rgba(239,68,68,.06); }

.r-card:hover .r-arrow {
  opacity: 1;
  transform: translateX(0);
  color: var(--primary);
}

/* ═══ 响应式：小屏幕单列 ═══ */
@media (max-width: 768px) {
  .grid { grid-template-columns: 1fr; }
  .page { padding: 20px 16px 40px; }
  .r-card { padding: 18px 16px; gap: 14px; }
  .r-icon { width: 42px; height: 42px; }
}
</style>
