/*
前端应用入口文件

作用：
  创建 Vue 应用实例，注册全局插件（Pinia/Router/ElementPlus），挂载到 DOM

关联文件：
  App.vue       ← 根组件，被挂载到 #app
  router/       ← 路由配置，被 app.use(router) 注册
  stores/       ← Pinia 状态管理，被 app.use(createPinia()) 注册
*/
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import './styles/global.css'
import App from './App.vue'
import router from './router'
import { useProgressBar } from './composables/useProgressBar'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 全局路由进度条
const { start, finish } = useProgressBar()
router.beforeEach((_to, _from) => {
  start()
})
router.afterEach(() => {
  finish()
})

app.mount('#app')
