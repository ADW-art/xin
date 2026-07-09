<!--
  StreamingText - Typing animation component for SSE streaming
  Handles incremental content appending during SSE.

  Props:
    content  - current text (grows during SSE streaming)
    speed    - ms per character chunk (default 20)

  Emits:
    done     - typing complete
-->
<template>
  <span class="streaming-text">
    <span v-html="displayedHtml" />
    <span v-if="!isTypingDone" class="streaming-cursor" />
  </span>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount, computed } from "vue"
import { marked } from "marked"
import DOMPurify from "dompurify"

const props = withDefaults(defineProps<{
  content: string
  speed?: number
}>(), { speed: 20 })

const emit = defineEmits<{ done: [] }>()

const revealed = ref("")
const isTypingDone = ref(false)
const targetText = ref("")  // full text target (grows with SSE)
let timer: ReturnType<typeof setInterval> | null = null
let charIndex = 0

const displayedHtml = computed(() => {
  if (!revealed.value) return ""
  const raw = marked.parse(revealed.value, { async: false }) as string
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS: ["p","ul","ol","li","pre","code","strong","em","a","h1","h2","h3","h4","h5","h6","blockquote","br","hr","table","thead","tbody","tr","th","td"],
    ALLOWED_ATTR: ["href", "target", "class"],
  })
})

function startOrContinue() {
  if (timer) return  // already typing
  if (!targetText.value) { isTypingDone.value = true; emit("done"); return }
  isTypingDone.value = false
  timer = setInterval(() => {
    const cs = Math.max(1, Math.floor(Math.random() * 3) + 1)
    const end = Math.min(charIndex + cs, targetText.value.length)
    revealed.value = targetText.value.slice(0, end)
    charIndex = end
    if (charIndex >= targetText.value.length) {
      stopTyping()
      isTypingDone.value = true
      emit("done")
    }
  }, props.speed)
}

function stopTyping() {
  if (timer !== null) { clearInterval(timer); timer = null }
}

// Watch content prop: when SSE appends, update target and continue typing
watch(() => props.content, (newVal) => {
  if (!newVal) return
  targetText.value = newVal
  // If we have more to reveal, start/continue typing
  if (charIndex < targetText.value.length) {
    startOrContinue()
  } else {
    stopTyping()
    isTypingDone.value = true
    emit("done")
  }
}, { immediate: true })

onBeforeUnmount(() => stopTyping())
</script>

<style scoped>
.streaming-text { display: inline; }
.streaming-cursor {
  display: inline-block; width: 2px; height: 1.1em;
  background: var(--primary); margin-left: 1px;
  vertical-align: text-bottom;
  animation: blink 0.6s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }
</style>