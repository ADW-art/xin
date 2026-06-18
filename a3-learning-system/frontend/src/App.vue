<!--
根组件

作用：
  整个应用的最外层容器，包含：
  1. 全局加载进度条（路由切换时自动显示）
  2. 路由出口 <router-view />

关联文件：
  router/index.ts  ← 定义各个路径对应哪个 View
  views/           ← 具体的页面组件（ChatView, Dashboard 等）
-->
<template>
  <div class="page-loader" :class="{ 'is-loading': isLoading }" aria-hidden="true" />
  <router-view />
  <!-- router-view：路由出口，URL 变化时自动切换渲染的组件 -->
</template>

<script setup lang="ts">
import { useProgressBar } from '@/composables/useProgressBar'

const { isLoading } = useProgressBar()
</script>
