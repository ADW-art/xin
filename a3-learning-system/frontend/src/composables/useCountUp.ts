/*
数字滚动画组合式函数（useCountUp）

作用：
  从 0 平滑滚动到目标数字，使用 easeOutExpo 缓动函数
  常用于仪表盘统计卡片、进度数字等需要动态展示的场景

用法：
  const { displayValue } = useCountUp(() => targetNumber, { duration: 1500 })
  // displayValue 是一个 ref<number>，在模板中直接使用即可
*/

import { ref, watch, onUnmounted } from 'vue'

export interface UseCountUpOptions {
  /** 动画总时长（毫秒），默认 1500 */
  duration?: number
}

function easeOutExpo(t: number): number {
  return t === 1 ? 1 : 1 - Math.pow(2, -10 * t)
}

export function useCountUp(target: () => number, options?: UseCountUpOptions) {
  const duration = options?.duration ?? 1500
  const displayValue = ref(0)
  let rafId: number | null = null

  function animate(from: number, to: number) {
    if (rafId !== null) cancelAnimationFrame(rafId)
    if (from === to) {
      displayValue.value = to
      return
    }

    const startTime = performance.now()
    const diff = to - from

    function step(currentTime: number) {
      const elapsed = currentTime - startTime
      const progress = Math.min(elapsed / duration, 1)
      const easedProgress = easeOutExpo(progress)
      displayValue.value = Math.round(from + diff * easedProgress)

      if (progress < 1) {
        rafId = requestAnimationFrame(step)
      } else {
        displayValue.value = to
        rafId = null
      }
    }

    rafId = requestAnimationFrame(step)
  }

  const stopWatch = watch(
    target,
    (newVal, oldVal) => {
      const from = typeof oldVal === 'number' && !isNaN(oldVal) ? oldVal : 0
      const to = typeof newVal === 'number' && !isNaN(newVal) ? newVal : 0
      animate(from, to)
    },
    { immediate: true }
  )

  onUnmounted(() => {
    if (rafId !== null) cancelAnimationFrame(rafId)
    stopWatch()
  })

  return { displayValue }
}
