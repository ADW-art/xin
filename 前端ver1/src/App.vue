<template>
  <div class="page-loader" :class="{ 'is-loading': isLoading }" aria-hidden="true">
    <div class="page-loader-bar" />
  </div>
  <router-view />
</template>

<script setup lang="ts">
import { useProgressBar } from '@/composables/useProgressBar'

const { isLoading } = useProgressBar()
</script>

<style>
.page-loader {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  z-index: 9999;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s ease;
}
.page-loader.is-loading {
  opacity: 1;
}
.page-loader-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--primary), #6366F1, var(--primary));
  background-size: 200% 100%;
  border-radius: 0 2px 2px 0;
  animation: loader-slide 1.2s ease-in-out infinite;
  width: 40%;
}
@keyframes loader-slide {
  0% {
    transform: translateX(-100%);
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
  100% {
    transform: translateX(350%);
    background-position: 0% 50%;
  }
}
</style>
