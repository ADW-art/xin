import { ref } from 'vue'

const isLoading = ref(false)

export function useProgressBar() {
  const start = () => {
    isLoading.value = true
  }
  const finish = () => {
    isLoading.value = false
  }
  const set = (_n: number) => {
    isLoading.value = true
  }
  return { isLoading, start, finish, set }
}
