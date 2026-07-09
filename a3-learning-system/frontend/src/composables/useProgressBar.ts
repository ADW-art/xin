/*
全局加载进度条组合式函数（useProgressBar）

作用：
  管理页面顶部加载进度条的显示/隐藏状态
  配合路由守卫使用，在页面切换时自动展示加载动画

用法：
  // 在 main.ts 中通过路由守卫控制
  import { useProgressBar } from '@/composables/useProgressBar'
  const { start, finish } = useProgressBar()
  router.beforeEach(() => start())
  router.afterEach(() => finish())

  // 在 App.vue 中绑定 CSS 类
  const { isLoading } = useProgressBar()
*/

import { ref } from 'vue'

const isLoading = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

export function useProgressBar() {
  function start() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    isLoading.value = true
  }

  function finish() {
    // 延迟隐藏，让用户看到完整的加载动画收尾
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      isLoading.value = false
      timer = null
    }, 300)
  }

  return { isLoading, start, finish }
}
