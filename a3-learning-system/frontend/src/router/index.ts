/*
路由配置

作用：
  定义前端路径与页面的对应关系，控制页面切换
  延迟加载（懒加载）每个页面组件，减少首屏加载体积

关联文件：
  main.ts            ← app.use(router) 注册路由
  views/             ← 路由指向的具体页面组件（ChatView, Dashboard 等）
  App.vue            ← 根组件中的 <router-view /> 根据路由渲染页面
*/
import { createRouter, createWebHistory } from 'vue-router'
// createRouter：创建路由实例
// createWebHistory：使用 HTML5 History 模式（URL 不带 #）

const router = createRouter({
  history: createWebHistory(),           // 使用 History 模式，URL 像 /chat 而不是 /#/chat
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue'),
      meta: { guest: true },
    },
    {
      path: '/',
      component: () => import('@/components/common/AppLayout.vue'),
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('@/views/Dashboard.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'chat',
          name: 'Chat',
          component: () => import('@/views/ChatView.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'profile',
          name: 'Profile',
          component: () => import('@/views/ProfileView.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'resources',
          name: 'Resources',
          component: () => import('@/views/ResourceView.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'resources/:id',
          name: 'ResourceDetail',
          component: () => import('@/views/ResourceDetail.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'assessment',
          name: 'Assessment',
          component: () => import('@/views/AssessmentView.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'learning-path',
          name: 'LearningPath',
          component: () => import('@/views/LearningPathView.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'custom-graph',
          name: 'CustomGraph',
          component: () => import('@/views/CustomGraphView.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'agents',
          name: 'AgentCenter',
          component: () => import('@/views/AgentCenter.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'bkt',
          name: 'BktCenter',
          component: () => import('@/views/BktCenter.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'rag',
          name: 'RagCenter',
          component: () => import('@/views/RagCenter.vue'),
          meta: { requiresAuth: true },
        },
      ],
    },
  ],
})

// ═══════════════════════════ Navigation Guard ═══════════════════════════
// beforeEnter 全局守卫：检查 JWT token 是否存在
//  - 无 token → 不在 /login → 重定向到 /login
//  - 有 token → 在 /login → 重定向到 /dashboard
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')

  if (to.meta.requiresAuth && !token) {
    // 需要登录但无 token → 跳转登录页
    next({ name: 'Login', query: { redirect: to.fullPath } })
  } else if (to.meta.guest && token) {
    // 已登录用户访问登录页 → 跳转控制台
    next({ name: 'Dashboard' })
  } else {
    next()
  }
})

export default router
