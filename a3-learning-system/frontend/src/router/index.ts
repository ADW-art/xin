import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/dashboard',
    },
    {
      path: '/dashboard',
      name: 'Dashboard',
      component: () => import('@/views/Dashboard.vue'),
    },
    {
      path: '/chat',
      name: 'Chat',
      component: () => import('@/views/ChatView.vue'),
    },
    {
      path: '/profile',
      name: 'Profile',
      component: () => import('@/views/ProfileView.vue'),
    },
    {
      path: '/resources',
      name: 'Resources',
      component: () => import('@/views/ResourceView.vue'),
    },
    {
      path: '/assessment',
      name: 'Assessment',
      component: () => import('@/views/AssessmentView.vue'),
    },
    {
      path: '/learning-path',
      name: 'LearningPath',
      component: () => import('@/views/LearningPathView.vue'),
    },
  ],
})

export default router
