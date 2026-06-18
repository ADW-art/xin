/*
用户状态管理（Pinia Store）

作用：
  管理用户认证状态（JWT token）、基本信息、学习画像
  提供登录/登出/获取用户信息/获取画像等操作

关联文件：
  views/Login.vue       ← 登录成功后调用 login() 写入状态
  views/ProfileView.vue ← 读取 profile 展示，调用 updateProfile() 修改
  components/common/AppLayout.vue ← 读取 userInfo 显示用户头像/昵称
  api/auth.ts           ← 底层请求函数
  api/profile.ts        ← 画像请求函数

使用方式：
  import { useUserStore } from '@/stores/user'
  const userStore = useUserStore()
  await userStore.login('myToken')
*/

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { login as loginApi, register as registerApi, getMe, type UserInfo } from '@/api/auth'
import {
  getProfile as getProfileApi,
  updateProfile as updateProfileApi,
  type LearningProfile,
  type ProfileUpdateData,
} from '@/api/profile'

export const useUserStore = defineStore('user', () => {
  // ============ 响应式状态 ============
  const token = ref<string | null>(localStorage.getItem('token'))    // JWT token，初始化时从 localStorage 读取
  const userInfo = ref<UserInfo | null>(null)                        // 用户基本信息（id/username/nickname/avatar）
  const profile = ref<LearningProfile | null>(null)                  // 6 维学习画像

  // ============ 计算属性 ============
  const isLoggedIn = computed(() => !!token.value)                   // 是否有 token（简化的登录判断）

  // ============ 操作方法 ============

  // 登录：保存 token 到 localStorage，然后拉取用户信息和画像
  async function login(accessToken: string) {
    token.value = accessToken
    localStorage.setItem('token', accessToken)
    await fetchUserInfo()
    await fetchProfile()
  }

  // 登出：清除 token 和所有状态，跳转到登录页
  function logout() {
    token.value = null
    userInfo.value = null
    profile.value = null
    localStorage.removeItem('token')
    // 使用 router 跳转（如果不在 setup 上下文中，window.location 作为降级）
    try {
      const router = useRouter()
      router.push('/login')
    } catch {
      window.location.href = '/login'
    }
  }

  // 从后端获取当前用户基本信息
  async function fetchUserInfo() {
    try {
      userInfo.value = await getMe()
    } catch (err) {
      // 如果获取失败可能是 token 过期，执行登出
      if ((err as { response?: { status?: number } }).response?.status === 401) {
        logout()
      }
    }
  }

  // 从后端获取当前用户的学习画像
  async function fetchProfile() {
    try {
      profile.value = await getProfileApi()
    } catch {
      // 画像数据可能尚未初始化，静默处理
    }
  }

  // 更新学习画像（部分字段）
  async function updateProfile(data: ProfileUpdateData) {
    try {
      profile.value = await updateProfileApi(data)
    } catch (err) {
      throw err
    }
  }

  // ============ 暴露给外部的属性和方法 ============
  return {
    token,
    userInfo,
    profile,
    isLoggedIn,
    login,
    logout,
    fetchUserInfo,
    fetchProfile,
    updateProfile,
  }
})
