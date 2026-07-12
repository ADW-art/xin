<template>
  <div class="app">
    <button class="hamburger" @click="sidebarOpen = !sidebarOpen" aria-label="菜单">
      <span :class="{ open: sidebarOpen }" />
    </button>
    <div v-if="sidebarOpen" class="sidebar-overlay" @click="sidebarOpen = false" />

    <aside class="sidebar" :class="{ 'sidebar-open': sidebarOpen }">
      <router-link to="/dashboard" class="logo">
        <div class="logo-dot" />
        <span class="logo-text">A3 Learning</span>
      </router-link>

      <nav class="nav-list" role="navigation" aria-label="主导航">
        <router-link
          v-for="m in menu"
          :key="m.to"
          :to="m.to"
          class="nav-link"
          active-class="active"
        >
          <el-icon :size="18"><component :is="m.icon" /></el-icon>
          <span>{{ m.label }}</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="user-info">
          <div class="user-avatar">
            <span class="user-avatar-text">{{ userInitial }}</span>
            <span class="user-status-dot" :class="{ online: user }" />
          </div>
          <div class="user-meta">
            <span class="user-name">{{ user?.nickname || user?.username || '游客' }}</span>
            <span class="user-role">学习者</span>
          </div>
        </div>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div class="tb-left">
          <span class="tb-breadcrumb">{{ currentPageLabel }}</span>
        </div>
        <div class="tb-right">
          <span v-if="user" class="logout" @click="doLogout">退出登录</span>
          <router-link v-else to="/login" class="login-btn">登录</router-link>
        </div>
      </header>

      <div class="content">
        <router-view v-slot="{ Component, route }">
          <transition :name="transitionName" mode="out-in">
            <component :is="Component" :key="route.fullPath" />
          </transition>
        </router-view>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'

const r = useRouter()
const route = useRoute()
const userStore = useUserStore()
const sidebarOpen = ref(false)
const user = computed(() => userStore.userInfo)

const menu = [
  { to: '/dashboard',     label: '智能中心',   icon: 'HomeFilled' },
  { to: '/chat',          label: 'AI 对话',    icon: 'ChatDotRound' },
  { to: '/resources',     label: '资源库',     icon: 'FolderOpened' },
  { to: '/learning-path', label: '学习路径',   icon: 'Guide' },
  { to: '/profile',       label: '学习画像',   icon: 'User' },
  { to: '/assessment',    label: '评估报告',   icon: 'DataAnalysis' },
  { to: '/agents',        label: 'Agent协作',  icon: 'Connection' },
  { to: '/bkt',           label: 'BKT追踪',    icon: 'TrendCharts' },
  { to: '/rag',           label: 'RAG检索',    icon: 'Search' },
]

const pageLabels: Record<string, string> = {
  Dashboard: '智能中心',
  AgentCenter: 'Agent 协作中心',
  BktCenter: 'BKT 知识追踪中心',
  Chat: 'AI 对话',
  ChatView: 'AI 对话',
  Profile: '学习画像',
  ProfileView: '学习画像',
  Resources: '资源库',
  ResourceView: '资源库',
  ResourceDetail: '资源详情',
  Assessment: '评估报告',
  AssessmentView: '评估报告',
  LearningPath: '学习路径',
  LearningPathView: '学习路径',
  CustomGraph: '自定义知识图谱',
  CustomGraphView: '自定义知识图谱',
  RagCenter: 'RAG 检索中心',
}

const currentPageLabel = computed(() => {
  return pageLabels[String(route.name)] || ''
})

const userInitial = computed(() => {
  const name = user.value?.nickname || user.value?.username || '?'
  return name.charAt(0).toUpperCase()
})

const transitionName = computed(() => {
  return route.name === 'ResourceDetail' ? 'page-scale' : 'page-slide'
})

onMounted(async () => {
  const t = localStorage.getItem('token')
  if (!t) return
  try {
    await userStore.fetchUserInfo()
  } catch {
    localStorage.removeItem('token')
  }
})

function doLogout() {
  userStore.logout()
}
</script>

<style scoped>
.app {
  display: flex;
  height: 100dvh;
  overflow: hidden;
}

/* ════════════════ SIDEBAR ════════════════ */
.sidebar {
  width: var(--sidebar-w);
  background: var(--bg-card);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  transition: transform 0.25s var(--ease-standard);
  position: relative;
  z-index: 100;
}
.sidebar::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 180px;
  background: rgba(37,99,235,.03);
  pointer-events: none;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  height: var(--header-h);
  padding: 0 var(--space-lg);
  text-decoration: none;
  font-size: var(--font-lg);
  font-weight: 800;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border);
  overflow: hidden;
  white-space: nowrap;
  position: relative;
  z-index: 1;
  transition: all var(--transition-fast);
}
.logo:hover { color: var(--primary); }
.logo-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--primary);
  flex-shrink: 0;
  box-shadow: 0 0 8px rgba(37,99,235,.3);
}
.logo-text {
  font-weight: 700;
  letter-spacing: -0.4px;
  color: var(--primary);
}

.nav-list {
  flex: 1;
  padding: var(--space-md) var(--space-sm) 0;
  position: relative;
  z-index: 1;
  overflow-y: auto;
}
.nav-link {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 0 var(--space-md);
  height: 44px;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  text-decoration: none;
  font-size: var(--font-base);
  font-weight: 500;
  transition: all var(--transition-normal) var(--ease-standard);
  margin-bottom: 3px;
  position: relative;
}
.nav-link .el-icon {
  transition: transform var(--transition-fast) var(--ease-bounce);
}
.nav-link:hover {
  color: var(--primary);
  background: rgba(37,99,235,.05);
}
.nav-link:hover .el-icon {
  transform: scale(1.12);
}
.nav-link.active {
  color: var(--primary);
  background: rgba(37,99,235,.08);
  font-weight: 600;
}
.nav-link.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  background: var(--primary);
  border-radius: 0 3px 3px 0;
}
.nav-link.active .el-icon {
  transform: scale(1.1);
}

.sidebar-footer {
  padding: var(--space-sm) var(--space-md);
  border-top: 1px solid var(--border);
  position: relative;
  z-index: 1;
  background: #FAFBFC;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 8px;
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
  cursor: default;
}
.user-info:hover {
  background: rgba(37,99,235,.04);
}
.user-avatar {
  position: relative;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.user-avatar-text {
  color: #fff;
  font-size: var(--font-sm);
  font-weight: 700;
}
.user-status-dot {
  position: absolute;
  bottom: -1px;
  right: -1px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--text-muted);
  border: 2px solid var(--bg-card);
  transition: all 0.3s;
}
.user-status-dot.online {
  background: var(--green);
}
.user-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.35;
}
.user-name {
  font-size: var(--font-sm);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-role {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

/* ════════════════ MAIN AREA ════════════════ */
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--bg-page);
  overflow: hidden;
}

.topbar {
  height: var(--header-h);
  background: rgba(255,255,255,.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-xl);
  flex-shrink: 0;
  font-size: var(--font-base);
  position: relative;
  z-index: 10;
  border-bottom: 1px solid var(--border);
}
.tb-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tb-breadcrumb {
  font-size: var(--font-base);
  color: var(--text-primary);
  font-weight: 600;
  letter-spacing: 0.2px;
}
.tb-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.logout {
  cursor: pointer;
  color: var(--text-muted);
  font-size: var(--font-sm);
  font-weight: 500;
  transition: all var(--transition-fast);
  padding: 6px 14px;
  border-radius: var(--radius-md);
  border: 1px solid transparent;
}
.logout:hover {
  color: var(--red);
  background: rgba(239,68,68,.06);
  border-color: rgba(239,68,68,.14);
}
.login-btn {
  color: var(--primary);
  text-decoration: none;
  font-size: var(--font-sm);
  font-weight: 600;
  transition: all var(--transition-fast);
  padding: 6px 18px;
  border-radius: var(--radius-md);
  border: 1px solid rgba(37,99,235,.15);
  background: rgba(37,99,235,.04);
}
.login-btn:hover {
  background: rgba(37,99,235,.1);
  border-color: rgba(37,99,235,.25);
}

.content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  position: relative;
  background: var(--bg-page);
}

/* ════════════════ Mobile ════════════════ */
.hamburger {
  display: none;
  position: fixed;
  top: 10px;
  left: 10px;
  z-index: 1100;
  width: 36px;
  height: 36px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-sm);
}
.hamburger span, .hamburger span::before, .hamburger span::after {
  display: block;
  width: 18px;
  height: 2px;
  background: var(--text-primary);
  border-radius: 2px;
  transition: all .25s;
}
.hamburger span { position: relative; }
.hamburger span::before, .hamburger span::after {
  content: '';
  position: absolute;
  left: 0;
}
.hamburger span::before { top: -5px; }
.hamburger span::after { top: 5px; }
.hamburger span.open { background: transparent; }
.hamburger span.open::before { top: 0; transform: rotate(45deg); }
.hamburger span.open::after { top: 0; transform: rotate(-45deg); }

.sidebar-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.4);
  z-index: 99;
}

@media (max-width: 768px) {
  .hamburger { display: flex; }
  .sidebar-overlay { display: block; }
  .sidebar {
    position: fixed;
    left: -260px;
    top: 0;
    bottom: 0;
    z-index: 1000;
    transition: left .25s;
    box-shadow: var(--shadow-lg);
  }
  .sidebar.sidebar-open { left: 0; }
  .topbar {
    padding-left: 56px;
    padding-right: var(--space-md);
  }
}
</style>
