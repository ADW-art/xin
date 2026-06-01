<!--
根组件

作用：
  整个应用的最外层容器，只包含路由出口 <router-view />
  所有页面切换由 vue-router 控制，根据 URL 渲染对应的 View

关联文件：
  router/index.ts  ← 定义各个路径对应哪个 View
  views/           ← 具体的页面组件（ChatView, Dashboard 等）
-->
<template>
  <router-view />
  <!-- router-view：路由出口，URL 变化时自动切换渲染的组件 -->
</template>
