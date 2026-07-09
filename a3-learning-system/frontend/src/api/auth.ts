/*
认证 API（auth）

作用：
  封装用户注册、登录、获取当前用户信息的 REST 请求
  所有接口基于后端的 /api/auth/* 路由

关联文件：
  stores/user.ts  ← 调用本文件的函数管理用户状态
  api/index.ts    ← 底层 axios 实例，提供 JWT 自动附加和 401 跳转

使用方式：
  import { login, register, getMe } from '@/api/auth'
*/

import api from './index'

// 后端 /api/auth/login 和 /api/auth/register 的响应结构
export interface AuthResponse {
  access_token: string
  token_type: string
}

// 后端 /api/auth/me 的响应结构
export interface UserInfo {
  id: number
  username: string
  nickname: string | null
  avatar_url: string | null
  created_at: string | null
}

// 登录：返回 JWT token 和用户信息
export async function login(username: string, password: string): Promise<AuthResponse> {
  const response = await api.post<AuthResponse>('/auth/login', {
    username,
    password,
  })
  return response.data
}

// 注册：创建新用户并返回 JWT token
export async function register(
  username: string,
  password: string,
  nickname?: string
): Promise<AuthResponse> {
  const response = await api.post<AuthResponse>('/auth/register', {
    username,
    password,
    nickname,
  })
  return response.data
}

// 获取当前登录用户信息（需要 JWT）
export async function getMe(): Promise<UserInfo> {
  const response = await api.get<UserInfo>('/auth/me')
  return response.data
}

// 登出：通知后端将当前 token 加入黑名单（需要 JWT）
export async function logout(): Promise<void> {
  await api.post('/auth/logout')
}
