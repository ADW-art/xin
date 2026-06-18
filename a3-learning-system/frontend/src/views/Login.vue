<template>
  <div class="login-wrap">
    <div class="login-card a-scale" :class="{ 'card-shake': shaking }">
      <!-- Brand -->
      <div class="card-brand">
        <div class="brand-icon">
          <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="48" height="48" rx="14" fill="url(#brandGrad)"/>
            <path d="M24 13L33 19.5V32.5L24 39L15 32.5V19.5L24 13Z" stroke="#fff" stroke-width="2" fill="none" stroke-linejoin="round"/>
            <circle cx="24" cy="26" r="5.5" fill="#fff" opacity="0.95"/>
            <defs>
              <linearGradient id="brandGrad" x1="0" y1="0" x2="48" y2="48">
                <stop offset="0%" stop-color="#2563EB"/>
                <stop offset="100%" stop-color="#6366F1"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
        <h1>A3 Learning</h1>
        <p class="brand-sub">个性化学习多智能体系统</p>
      </div>

      <!-- Error banner -->
      <transition name="error-fade">
        <div v-if="errorMsg" class="error-banner" @click="errorMsg = ''">
          <el-icon :size="16"><WarningFilled /></el-icon>
          <span>{{ errorMsg }}</span>
        </div>
      </transition>

      <!-- Form -->
      <el-form
        ref="formRef"
        :model="form"
        label-position="top"
        size="large"
        @submit.prevent="handleSubmit"
      >
        <el-form-item label="用户名">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            :disabled="loading"
            @keydown.enter="focusPassword"
          />
        </el-form-item>

        <el-form-item label="密码">
          <el-input
            ref="passwordInputRef"
            v-model="form.password"
            :type="showPassword ? 'text' : 'password'"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            :disabled="loading"
            :suffix-icon="showPassword ? View : Hide"
            @suffix-click="showPassword = !showPassword"
            @keydown.enter="handleSubmit"
          />
        </el-form-item>

        <transition name="error-fade">
          <el-form-item v-if="isReg" label="昵称">
            <el-input
              v-model="form.nickname"
              placeholder="给自己起个名字"
              :prefix-icon="UserFilled"
              :disabled="loading"
            />
          </el-form-item>
        </transition>

        <div v-if="!isReg" class="form-extras">
          <el-checkbox v-model="rememberMe" size="small" :disabled="loading">
            记住用户名
          </el-checkbox>
        </div>

        <el-button
          type="primary"
          :loading="loading"
          size="large"
          class="submit-btn"
          :disabled="loading"
          @click="handleSubmit"
          :aria-label="isReg ? '注册新账号' : '登录账号'"
        >
          <template v-if="loading">
            <span>{{ isReg ? '注册中...' : '登录中...' }}</span>
          </template>
          <template v-else>
            {{ isReg ? '注 册' : '登 录' }}
          </template>
        </el-button>
      </el-form>

      <p class="switch-link" @click="toggleMode">
        {{ isReg ? '已有账号？去登录' : '没有账号？去注册' }}
      </p>
    </div>

    <p class="login-footer">科大讯飞 &middot; A3 学习系统</p>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, UserFilled, View, Hide, WarningFilled } from '@element-plus/icons-vue'
import { login as authLogin, register as authRegister } from '@/api/auth'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const loading = ref(false)
const isReg = ref(false)
const showPassword = ref(false)
const errorMsg = ref('')
const shaking = ref(false)
const rememberMe = ref(false)
const passwordInputRef = ref<{ focus: () => void } | null>(null)

const form = reactive({
  username: '',
  password: '',
  nickname: '',
})

onMounted(() => {
  const saved = localStorage.getItem('a3_remembered_username')
  if (saved) {
    form.username = saved
    rememberMe.value = true
  }
})

function focusPassword() {
  passwordInputRef.value?.focus()
}

function triggerShake() {
  shaking.value = true
  setTimeout(() => { shaking.value = false }, 500)
}

function toggleMode() {
  isReg.value = !isReg.value
  errorMsg.value = ''
}

async function handleSubmit() {
  if (!form.username.trim() || !form.password.trim()) {
    errorMsg.value = '请填写用户名和密码'
    triggerShake()
    return
  }
  if (form.password.length < 6) {
    errorMsg.value = '密码长度不能少于 6 位'
    triggerShake()
    return
  }

  loading.value = true
  errorMsg.value = ''

  try {
    let token: string

    if (isReg.value) {
      const res = await authRegister(
        form.username.trim(),
        form.password,
        form.nickname.trim() || undefined
      )
      token = res.access_token
    } else {
      const res = await authLogin(form.username.trim(), form.password)
      token = res.access_token
    }

    await userStore.login(token)

    if (!isReg.value && rememberMe.value) {
      localStorage.setItem('a3_remembered_username', form.username.trim())
    } else {
      localStorage.removeItem('a3_remembered_username')
    }

    ElMessage.success(isReg.value ? '注册成功，欢迎加入！' : '登录成功')
    const redirect = route.query.redirect as string | undefined
    router.push(redirect || '/dashboard')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string }; status?: number } }
    const detail = err?.response?.data?.detail
    if (detail) {
      errorMsg.value = detail
    } else if (err?.response?.status === 401) {
      errorMsg.value = '用户名或密码错误'
    } else if (err?.response?.status === 409) {
      errorMsg.value = '用户名已存在'
    } else {
      errorMsg.value = '网络连接失败，请检查网络后重试'
    }
    triggerShake()
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* ═══════════ Page ═══════════ */
.login-wrap {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100dvh;
  background: var(--bg-page);
}

/* ═══════════ Card ═══════════ */
.login-card {
  width: 420px;
  padding: 44px 40px 36px;
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
}

.card-shake {
  animation: cardShake 0.5s ease both;
}
@keyframes cardShake {
  0%, 100% { transform: translateX(0); }
  10% { transform: translateX(-8px); }
  20% { transform: translateX(8px); }
  30% { transform: translateX(-6px); }
  40% { transform: translateX(6px); }
  50% { transform: translateX(-4px); }
  60% { transform: translateX(4px); }
  70% { transform: translateX(-2px); }
  80% { transform: translateX(2px); }
  90% { transform: translateX(-1px); }
}

/* ═══════════ Brand ═══════════ */
.card-brand {
  text-align: center;
  margin-bottom: 28px;
}
.brand-icon {
  display: inline-flex;
  margin-bottom: 14px;
}
.brand-icon svg {
  width: 52px;
  height: 52px;
}
.brand-icon :deep(rect) {
  fill: var(--primary);
}
.card-brand h1 {
  font-size: var(--font-3xl);
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}
.brand-sub {
  font-size: var(--font-sm);
  color: var(--text-secondary);
  margin-top: 6px;
}

/* ═══════════ Error ═══════════ */
.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 16px;
  background: var(--red-light);
  border: 1px solid var(--red-light);
  border-radius: var(--radius-md);
  color: var(--red);
  font-size: var(--font-sm);
  cursor: pointer;
}
.error-fade-enter-active,
.error-fade-leave-active {
  transition: all 0.2s ease;
}
.error-fade-enter-from,
.error-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ═══════════ Form ═══════════ */
.form-extras {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.submit-btn {
  width: 100%;
  height: 46px;
  margin-top: 4px;
  font-size: var(--font-lg);
  font-weight: 600;
  letter-spacing: 2px;
  border-radius: var(--radius-md);
  transition: background var(--transition-fast) var(--ease-standard) !important;
}

/* ═══════════ Toggle ═══════════ */
.switch-link {
  text-align: center;
  margin-top: 20px;
  color: var(--primary);
  cursor: pointer;
  font-size: var(--font-sm);
  transition: color var(--transition-fast);
  user-select: none;
}
.switch-link:hover { color: var(--primary-hover); }

/* ═══════════ Footer ═══════════ */
.login-footer {
  margin-top: var(--space-lg);
  font-size: var(--font-xs);
  color: var(--text-muted);
}

/* ═══════════ Element Plus overrides ═══════════ */
:deep(.el-form-item) {
  margin-bottom: 18px;
}
:deep(.el-input__wrapper) {
  border-radius: var(--radius-md);
  background: var(--bg-input) !important;
  border: 1px solid var(--border) !important;
  box-shadow: none !important;
  transition: border-color var(--transition-fast) ease;
}
:deep(.el-input__wrapper:hover) {
  border-color: var(--border) !important;
}
:deep(.el-input.is-focus .el-input__wrapper) {
  border-color: var(--primary) !important;
}
:deep(.el-form-item__label) {
  color: var(--text-secondary) !important;
}
:deep(.el-checkbox__label) {
  font-size: var(--font-sm);
  color: var(--text-secondary);
}
</style>
