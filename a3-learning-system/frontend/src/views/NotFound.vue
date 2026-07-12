<!--
404 Not Found 页面

作用：
  当用户访问不存在的路由时显示此页面，引导用户返回首页
  避免空白页面

关联文件：
  router/index.ts  ← 注册通配路由
--><template>
  <div class="not-found-page">
    <div class="not-found-card">
      <div class="not-found-code">404</div>
      <div class="not-found-divider" />
      <h2 class="not-found-title">页面未找到</h2>
      <p class="not-found-desc">您访问的页面不存在或已被移除</p>
      <div class="not-found-actions">
        <el-button type="primary" size="large" @click="$router.push('/dashboard')">
          返回首页
        </el-button>
        <el-button size="large" @click="$router.back()">
          返回上页
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.not-found-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--bg-page);
  padding: var(--space-lg);
}

.not-found-card {
  text-align: center;
  background: var(--bg-card);
  border-radius: 16px;
  padding: var(--space-2xl) var(--space-3xl);
  box-shadow: var(--shadow-lg);
  max-width: 460px;
  width: 100%;
}

.not-found-code {
  font-size: 96px;
  font-weight: 800;
  color: var(--primary);
  line-height: 1;
  letter-spacing: -2px;
}

.not-found-divider {
  width: 60px;
  height: 3px;
  background: var(--primary);
  margin: var(--space-lg) auto;
  border-radius: 2px;
}

.not-found-title {
  font-size: var(--font-2xl);
  color: var(--text-primary);
  margin: 0 0 var(--space-sm) 0;
}

.not-found-desc {
  font-size: var(--font-md);
  color: var(--text-secondary);
  margin: 0 0 var(--space-xl) 0;
}

.not-found-actions {
  display: flex;
  gap: var(--space-md);
  justify-content: center;
}
</style>
