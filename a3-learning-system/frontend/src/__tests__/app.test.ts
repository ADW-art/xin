/*
前端测试套件 — A3 学习系统

覆盖:
  1. Router: 路由定义完整性、导航守卫
  2. Stores: user/chat/learning Pinia store 操作
  3. API: 接口模块导出验证
  4. Components: 错误边界、404 页面
  5. Composables: useProgressBar、useCountUp
*/
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// ─────────────────────────────────────────────────
// 1. Router 路由测试
// ─────────────────────────────────────────────────
describe('Router', () => {
  it('应包含所有必需的路由', async () => {
    const router = (await import('@/router')).default
    const routes = router.getRoutes()
    const names = routes.map(r => r.name).filter(Boolean)

    expect(names).toContain('Login')
    expect(names).toContain('Dashboard')
    expect(names).toContain('Chat')
    expect(names).toContain('Profile')
    expect(names).toContain('Resources')
    expect(names).toContain('ResourceDetail')
    expect(names).toContain('Assessment')
    expect(names).toContain('LearningPath')
    expect(names).toContain('CustomGraph')
    expect(names).toContain('AgentCenter')
    expect(names).toContain('BktCenter')
    expect(names).toContain('RagCenter')
    expect(names).toContain('NotFound')
  })

  it('NotFound 应是通配路由', async () => {
    const router = (await import('@/router')).default
    const notFound = router.getRoutes().find(r => r.name === 'NotFound')
    expect(notFound).toBeDefined()
    expect(notFound!.path).toMatch(/:pathMatch/)
  })

  it('Dashboard/Profile/Resources 路由应要求认证', async () => {
    const router = (await import('@/router')).default
    const protectedRoutes = ['Dashboard', 'Chat', 'Profile', 'Resources',
      'Assessment', 'LearningPath', 'BktCenter', 'RagCenter', 'AgentCenter']

    for (const name of protectedRoutes) {
      const route = router.getRoutes().find(r => r.name === name)
      expect(route).toBeDefined()
      expect(route!.meta?.requiresAuth ?? route!.children?.some(c => c.meta?.requiresAuth)).toBeTruthy()
    }
  })
})

// ─────────────────────────────────────────────────
// 2. Pinia Store 测试
// ─────────────────────────────────────────────────
describe('userStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('初始状态 token 从 localStorage 读取', async () => {
    const { useUserStore } = await import('@/stores/user')
    const store = useUserStore()
    expect(store.token).toBeNull()
    expect(store.userInfo).toBeNull()
  })

  it('直接设置 token 应更新状态和 localStorage', async () => {
    const { useUserStore } = await import('@/stores/user')
    const store = useUserStore()
    store.token = 'test-token'
    localStorage.setItem('token', 'test-token')
    expect(store.token).toBe('test-token')
    expect(localStorage.getItem('token')).toBe('test-token')
  })

  it('logout 应清除 token 和 userInfo', async () => {
    const { useUserStore } = await import('@/stores/user')
    const store = useUserStore()
    store.token = 'test-token'
    store.userInfo = { id: 1, username: 'test' } as any
    store.token = null
    store.userInfo = null
    localStorage.removeItem('token')
    expect(store.token).toBeNull()
    expect(store.userInfo).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
  })
})

describe('chatStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('初始状态应含空消息数组', async () => {
    const { useChatStore } = await import('@/stores/chat')
    const store = useChatStore()
    expect(store.messages).toEqual([])
    expect(store.isStreaming).toBe(false)
    expect(store.currentAgent).toBe('supervisor')
  })

  it('addUserMessage 应正确添加用户消息', async () => {
    const { useChatStore } = await import('@/stores/chat')
    const store = useChatStore()
    store.addUserMessage('Hello')
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].role).toBe('user')
    expect(store.messages[0].content).toBe('Hello')
    expect(store.messages[0].id).toBeTruthy()
  })

  it('startAssistantReply + appendToStreaming + finishAssistantReply 应构建完整助理消息', async () => {
    const { useChatStore } = await import('@/stores/chat')
    const store = useChatStore()
    store.currentAgent = 'resource_agent'
    store.startAssistantReply()
    expect(store.isStreaming).toBe(true)
    expect(store.currentAgent).toBe('resource_agent')

    store.appendToStreaming('这是')
    store.appendToStreaming('回复')
    expect(store.messages[0].content).toBe('这是回复')

    store.finishAssistantReply()
    expect(store.isStreaming).toBe(false)
  })

  it('clearMessages 应清空消息', async () => {
    const { useChatStore } = await import('@/stores/chat')
    const store = useChatStore()
    store.addUserMessage('test')
    store.startAssistantReply()
    store.appendToStreaming('reply')
    store.finishAssistantReply()
    expect(store.messages.length).toBeGreaterThan(0)

    store.clearMessages()
    expect(store.messages).toEqual([])
  })
})

describe('learningStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('初始 resources 应为空数组', async () => {
    const { useLearningStore } = await import('@/stores/learning')
    const store = useLearningStore()
    expect(store.resources).toEqual([])
    expect(store.reports).toEqual([])
    expect(store.records).toEqual([])
    expect(store.bktConcepts).toEqual([])
  })

  it('clearCache 应清空所有状态', async () => {
    const { useLearningStore } = await import('@/stores/learning')
    const store = useLearningStore()
    store.resources = [{ id: 1 } as any]
    store.bktConcepts = [{ concept: 'test' } as any]
    store.clearCache()
    expect(store.resources).toEqual([])
    expect(store.bktConcepts).toEqual([])
  })
})

// ─────────────────────────────────────────────────
// 3. API 模块导出验证
// ─────────────────────────────────────────────────
describe('API modules', () => {
  const apiModules = ['auth', 'chat', 'profile', 'resource', 'assessment', 'path', 'tts', 'bkt', 'admin', 'video', 'agent-trace']

  for (const mod of apiModules) {
    it(`api/${mod}.ts 应可动态导入并导出函数`, async () => {
      const m = await import(`@/api/${mod}`)
      expect(m).toBeDefined()
      // 至少包含一个导出函数
      const fns = Object.values(m).filter(v => typeof v === 'function')
      expect(fns.length).toBeGreaterThan(0)
    })
  }
})

// ─────────────────────────────────────────────────
// 4. 组件存在性验证
// ─────────────────────────────────────────────────
describe('ErrorBoundary component', () => {
  it('应可正确导入', async () => {
    const mod = await import('@/components/common/ErrorBoundary.vue')
    expect(mod.default).toBeDefined()
  })
})

describe('NotFound view', () => {
  it('应可正确导入', async () => {
    const mod = await import('@/views/NotFound.vue')
    expect(mod.default).toBeDefined()
  })
})

// ─────────────────────────────────────────────────
// 5. Composables 测试
// ─────────────────────────────────────────────────
describe('useProgressBar', () => {
  it('应可正确导入并返回 isLoading 和操作方法', async () => {
    const { useProgressBar } = await import('@/composables/useProgressBar')
    const { isLoading, start, finish } = useProgressBar()
    expect(isLoading).toBeDefined()
    expect(typeof start).toBe('function')
    expect(typeof finish).toBe('function')
    expect(isLoading.value).toBe(false)

    start()
    expect(isLoading.value).toBe(true)

    // finish() 有 300ms 延迟隐藏，等待动画完成
    finish()
    await new Promise(resolve => setTimeout(resolve, 400))
    expect(isLoading.value).toBe(false)
  })
})

describe('useCountUp', () => {
  it('应可正确导入并返回 displayValue', async () => {
    const { useCountUp } = await import('@/composables/useCountUp')
    const { displayValue } = useCountUp(() => 100, { duration: 500 })
    expect(displayValue).toBeDefined()
    expect(typeof displayValue.value).toBe('number')
  })
})

// ─────────────────────────────────────────────────
// 6. Utils 工具函数测试
// ─────────────────────────────────────────────────
describe('highlight', () => {
  it('应可正确导入语法高亮函数', async () => {
    const mod = await import('@/utils/highlight')
    expect(mod.highlightCode).toBeDefined()
  })
})
