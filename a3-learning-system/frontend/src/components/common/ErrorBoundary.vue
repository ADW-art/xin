<!--
全局错误边界组件

作用：
  捕获子组件树中未被处理的渲染错误，显示友好的错误页面
  防止单个组件崩溃导致整个应用白屏

使用方式：
  在 App.vue 或 main.ts 中全局注册，包裹 router-view

关联文件：
  App.vue  ← 包裹 router-view
--><template>
  <slot v-if="!hasError" />
  <div v-else class="error-boundary-page">
    <div class="error-boundary-card">
      <div class="error-icon">
        <el-icon :size="48"><WarningFilled /></el-icon>
      </div>
      <h2 class="error-title">页面渲染异常</h2>
      <p class="error-desc">页面组件加载或渲染时出现错误，请尝试刷新页面</p>
      <p v-if="errorMessage" class="error-detail">{{ errorMessage }}</p>
      <div class="error-actions">
        <el-button type="primary" size="large" @click="handleRefresh">
          刷新页面
        </el-button>
        <el-button size="large" @click="handleGoHome">
          返回首页
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const hasError = ref(false)
const errorMessage = ref('')

onErrorCaptured((err: unknown) => {
  hasError.value = true
  errorMessage.value = err instanceof Error ? err.message : String(err)
  console.error('[ErrorBoundary] 捕获到渲染错误:', err)
  return false   // 阻止错误继续向上传播
})

function handleRefresh() {
  window.location.reload()
}

function handleGoHome() {
  hasError.value = false
  errorMessage.value = ''
  router.push('/dashboard')
}
</script>

<style scoped>
.error-boundary-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--bg-page);
  padding: var(--space-lg);
}

.error-boundary-card {
  text-align: center;
  background: var(--bg-card);
  border-radius: 16px;
  padding: var(--space-2xl) var(--space-3xl);
  box-shadow: var(--shadow-lg);
  max-width: 500px;
  width: 100%;
}

.error-icon {
  color: var(--warning, #F59E0B);
  margin-bottom: var(--space-lg);
}

.error-title {
  font-size: var(--font-2xl);
  color: var(--text-primary);
  margin: 0 0 var(--space-sm) 0;
}

.error-desc {
  font-size: var(--font-md);
  color: var(--text-secondary);
  margin: 0 0 var(--space-sm) 0;
}

.error-detail {
  font-size: var(--font-sm);
  color: var(--text-muted);
  background: var(--bg-input);
  border-radius: 8px;
  padding: var(--space-md);
  margin: var(--space-md) 0;
  word-break: break-all;
  max-height: 120px;
  overflow-y: auto;
}

.error-actions {
  display: flex;
  gap: var(--space-md);
  justify-content: center;
  margin-top: var(--space-xl);
}
</style>
