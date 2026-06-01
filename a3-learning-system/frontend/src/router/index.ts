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
        },
        {
          path: 'chat',
          name: 'Chat',
          component: () => import('@/views/ChatView.vue'),
        },
        {
          path: 'profile',
          name: 'Profile',
          component: () => import('@/views/ProfileView.vue'),
        },
        {
          path: 'resources',
          name: 'Resources',
          component: () => import('@/views/ResourceView.vue'),
        },
        {
          path: 'assessment',
          name: 'Assessment',
          component: () => import('@/views/AssessmentView.vue'),
        },
        {
          path: 'learning-path',
          name: 'LearningPath',
          component: () => import('@/views/LearningPathView.vue'),
        },
      ],
    },
  ],
})

export default router
