<template>
  <el-container class="layout">
    <div class="sidebar">
      <div class="logo">
        <el-icon :size="24"><DataAnalysis /></el-icon>
        <span>A3 Learning</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="transparent"
        text-color="#a3b1cc"
        active-text-color="#fff"
      >
        <el-menu-item index="/dashboard">
          <el-icon><HomeFilled /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>AI 对话</span>
        </el-menu-item>
        <el-menu-item index="/profile">
          <el-icon><User /></el-icon>
          <span>学习画像</span>
        </el-menu-item>
        <el-menu-item index="/resources">
          <el-icon><FolderOpened /></el-icon>
          <span>资源库</span>
        </el-menu-item>
        <el-menu-item index="/assessment">
          <el-icon><TrendCharts /></el-icon>
          <span>评估报告</span>
        </el-menu-item>
        <el-menu-item index="/learning-path">
          <el-icon><Guide /></el-icon>
          <span>学习路径</span>
        </el-menu-item>
      </el-menu>
    </div>
    <el-container>
      <el-header>
        <div class="header-left">
          <el-icon><UserFilled /></el-icon>
          <span>{{ userInfo?.nickname || userInfo?.username || '未登录' }}</span>
        </div>
        <el-button text v-if="userInfo" @click="logout">退出登录</el-button>
        <el-button type="primary" size="small" v-else @click="$router.push('/login')">登录</el-button>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/index'

const route = useRoute()
const router = useRouter()
const userInfo = ref<any>(null)

onMounted(async () => {
  const token = localStorage.getItem('token')
  if (!token) return
  try {
    const res = await api.get('/auth/me')
    userInfo.value = res.data
  } catch {
    localStorage.removeItem('token')
  }
})

function logout() {
  localStorage.removeItem('token')
  userInfo.value = null
  router.push('/login')
}
</script>

<style scoped>
.layout {
  height: 100vh;
}
.sidebar {
  width: var(--sidebar-width);
  background: linear-gradient(180deg, #1a2332 0%, #16212e 100%);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #fff;
  font-size: 18px;
  font-weight: 700;
  padding: 18px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  letter-spacing: 0.5px;
}
.sidebar :deep(.el-menu) {
  border-right: none;
  flex: 1;
  padding: 8px 0;
}
.sidebar :deep(.el-menu-item) {
  margin: 2px 8px;
  border-radius: 8px;
  height: 44px;
  line-height: 44px;
  transition: all 0.2s;
}
.sidebar :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.06) !important;
}
.sidebar :deep(.el-menu-item.is-active) {
  background: rgba(64, 158, 255, 0.2) !important;
  font-weight: 600;
}
.sidebar :deep(.el-icon) {
  font-size: 18px;
}
.el-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--header-height);
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  padding: 0 24px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}
.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #303133;
  font-size: 14px;
}
.el-main {
  background: #f7f8fa;
  padding: 0;
}
</style>
