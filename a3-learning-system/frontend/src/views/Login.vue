<template>
  <div class="login-page">
    <div class="card">
      <div class="brand">
        <el-icon :size="36"><DataAnalysis /></el-icon>
        <h1>A3 Learning</h1>
      </div>
      <p class="subtitle">{{ isRegister ? '创建账号开始学习' : '登录你的学习空间' }}</p>
      <el-form :model="form" label-position="top">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" size="large" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" size="large" show-password />
        </el-form-item>
        <el-form-item v-if="isRegister" label="昵称">
          <el-input v-model="form.nickname" placeholder="给自己起个名字（选填）" size="large" />
        </el-form-item>
        <el-button type="primary" :loading="loading" size="large" style="width:100%; margin-top:8px" @click="submit">
          {{ isRegister ? '注册' : '登录' }}
        </el-button>
      </el-form>
      <p class="switch" @click="toggle">
        {{ isRegister ? '已有账号？去登录' : '没有账号？去注册' }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api/index'

const router = useRouter()
const loading = ref(false)
const isRegister = ref(false)
const form = ref({ username: '', password: '', nickname: '' })

function toggle() {
  isRegister.value = !isRegister.value
}

async function submit() {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  loading.value = true
  try {
    const url = isRegister.value ? '/auth/register' : '/auth/login'
    const body: any = { username: form.value.username, password: form.value.password }
    if (isRegister.value && form.value.nickname) body.nickname = form.value.nickname
    const res = await api.post(url, body)
    localStorage.setItem('token', res.data.access_token)
    ElMessage.success(isRegister.value ? '注册成功' : '登录成功')
    router.push('/dashboard')
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '请求失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background: linear-gradient(135deg, #e8f0fe 0%, #f7f8fa 50%, #ecf5ff 100%);
}
.card {
  width: 400px;
  padding: 40px 36px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06);
}
.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 4px;
  color: #409eff;
}
.brand h1 {
  font-size: 24px;
  font-weight: 700;
}
.subtitle {
  text-align: center;
  color: #909399;
  font-size: 14px;
  margin-bottom: 28px;
}
.switch {
  text-align: center;
  margin-top: 20px;
  color: #409eff;
  cursor: pointer;
  font-size: 14px;
}
.switch:hover {
  opacity: 0.8;
}
</style>
