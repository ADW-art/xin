<template>
  <div class="dashboard">
    <div class="welcome">
      <h2>欢迎回来</h2>
      <p>你的个性化学习系统已就绪，选择一个功能开始吧</p>
    </div>
    <div class="grid">
      <el-card
        v-for="c in cards"
        :key="c.title"
        :class="['card', c.accent]"
        shadow="hover"
        @click="$router.push(c.link)"
      >
        <div class="card-head">
          <div class="card-icon">
            <el-icon :size="28"><component :is="c.icon" /></el-icon>
          </div>
          <div class="card-title">{{ c.title }}</div>
        </div>
        <div class="card-desc">{{ c.desc }}</div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
const cards = [
  { icon: 'ChatDotRound', title: 'AI 对话', desc: '与多 Agent 系统对话，获取个性化学习帮助', link: '/chat', accent: 'accent-blue' },
  { icon: 'User', title: '学习画像', desc: '查看你的 6 维学习画像，了解自己的学习特征', link: '/profile', accent: 'accent-green' },
  { icon: 'FolderOpened', title: '资源库', desc: '浏览 AI 为你生成的个性化学习资源', link: '/resources', accent: 'accent-purple' },
  { icon: 'TrendCharts', title: '评估报告', desc: '查看多维度学习评估和改进建议', link: '/assessment', accent: 'accent-orange' },
  { icon: 'Guide', title: '学习路径', desc: '可视化你的个性化学习路线图', link: '/learning-path', accent: 'accent-teal' },
]
</script>

<style scoped>
.dashboard {
  padding: 32px;
  max-width: 1100px;
}
.welcome {
  margin-bottom: 32px;
}
.welcome h2 {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
  margin-bottom: 8px;
}
.welcome p {
  color: #909399;
  font-size: 14px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}
.card {
  cursor: pointer;
  transition: all 0.25s;
  border: 1px solid #ebeef5;
}
.card:hover {
  transform: translateY(-4px);
}
.card-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.card-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.accent-blue .card-icon  { background: #ecf5ff; color: #409eff; }
.accent-green .card-icon { background: #edf8e8; color: #67c23a; }
.accent-purple .card-icon{ background: #f4f0fe; color: #7c3aed; }
.accent-orange .card-icon{ background: #fef0e6; color: #e6a23c; }
.accent-teal .card-icon  { background: #e6f7f4; color: #20a39e; }
.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.card-desc {
  font-size: 13px;
  color: #909399;
  line-height: 1.6;
  padding-left: 60px;
}
</style>
