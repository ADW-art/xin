<template>
  <div class="app-skeleton" :class="type">
    <template v-if="type === 'card'">
      <div class="skeleton-card" v-for="i in count" :key="i">
        <div class="sk-header">
          <div class="sk-avatar shimmer" />
          <div class="sk-lines">
            <div class="sk-line shimmer sk-line-title" />
            <div class="sk-line shimmer sk-line-sub" />
          </div>
        </div>
        <div class="sk-line shimmer sk-line-full mt-sm" />
        <div class="sk-line shimmer sk-line-wide" />
        <div class="sk-line shimmer sk-line-narrow" />
      </div>
    </template>
    <template v-else-if="type === 'list'">
      <div class="skeleton-list" v-for="i in count" :key="i">
        <div class="sk-icon shimmer" />
        <div class="sk-lines sk-flex-1">
          <div class="sk-line shimmer sk-line-title" />
          <div class="sk-line shimmer sk-line-sub" />
        </div>
      </div>
    </template>
    <template v-else-if="type === 'text'">
      <div class="skeleton-text-group">
        <div class="sk-line shimmer" v-for="i in lines" :key="i" :class="skTextClass(i)" />
      </div>
    </template>
    <template v-else-if="type === 'profile'">
      <div class="skeleton-profile">
        <div class="sk-banner shimmer" />
        <div class="sk-avatar-wrap">
          <div class="sk-avatar-circle shimmer" />
        </div>
        <div class="sk-line shimmer sk-name" />
        <div class="sk-line shimmer sk-tag" />
        <div class="sk-stats">
          <div class="sk-stat">
            <div class="sk-line shimmer sk-stat-val" />
            <div class="sk-line shimmer sk-stat-label" />
          </div>
          <div class="sk-stat">
            <div class="sk-line shimmer sk-stat-val" />
            <div class="sk-line shimmer sk-stat-label" />
          </div>
        </div>
      </div>
    </template>
    <template v-else-if="type === 'stat'">
      <div class="skeleton-stats">
        <div class="sk-stat-chip shimmer" v-for="i in count" :key="i" />
      </div>
    </template>
    <template v-else>
      <div class="skeleton-page">
        <div class="sk-line shimmer sk-page-title" />
        <div class="sk-grid">
          <div class="sk-card-lg shimmer" v-for="i in 3" :key="i" />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
interface Props {
  type?: 'card' | 'list' | 'text' | 'profile' | 'stat' | 'page'
  count?: number
  lines?: number
}
withDefaults(defineProps<Props>(), {
  type: 'card',
  count: 3,
  lines: 3,
})

function skTextClass(i: number): string {
  const widths = ['sk-line-full', 'sk-line-wide', 'sk-line-narrow', 'sk-line-medium', 'sk-line-full', 'sk-line-wide']
  return widths[(i - 1) % widths.length]
}
</script>

<style scoped>
.shimmer {
  background: linear-gradient(90deg, var(--bg-muted) 25%, var(--border) 50%, var(--bg-muted) 75%);
  background-size: 200% 100%;
  animation: shimmer-anim 1.5s infinite;
  border-radius: var(--radius-sm);
}
@keyframes shimmer-anim {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.mt-sm { margin-top: var(--space-sm); }
.sk-flex-1 { flex: 1; }

.sk-line {
  border-radius: var(--radius-sm);
}
.sk-line-title { width: 40%; height: 14px; }
.sk-line-sub { width: 65%; height: 12px; margin-top: 6px; }
.sk-line-full { width: 100%; height: 10px; }
.sk-line-wide { width: 85%; height: 10px; margin-top: 8px; }
.sk-line-narrow { width: 60%; height: 10px; margin-top: 8px; }
.sk-line-medium { width: 75%; height: 10px; margin-top: 8px; }

.skeleton-card {
  padding: var(--space-md);
  margin-bottom: var(--space-sm);
}
.sk-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.sk-avatar {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}
.sk-avatar-circle {
  width: 44px;
  height: 44px;
  border-radius: 50%;
}
.sk-lines {
  display: flex;
  flex-direction: column;
}

.skeleton-list {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
}
.sk-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.skeleton-text-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 0;
}

.skeleton-profile {
  position: relative;
  padding-top: 0;
}
.sk-banner {
  height: 52px;
  margin: calc(-1 * var(--space-md)) calc(-1 * var(--space-md)) 0;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}
.sk-avatar-wrap {
  display: flex;
  justify-content: center;
  margin-top: -22px;
}
.sk-name {
  width: 80px;
  height: 14px;
  margin: var(--space-sm) auto var(--space-xs);
}
.sk-tag {
  width: 60px;
  height: 10px;
  margin: 0 auto;
}
.sk-stats {
  display: flex;
  justify-content: center;
  gap: var(--space-xl);
  margin-top: var(--space-md);
  padding-top: var(--space-md);
  border-top: 1px dashed var(--border);
}
.sk-stat {
  text-align: center;
}
.sk-stat-val {
  width: 30px;
  height: 18px;
  margin: 0 auto;
}
.sk-stat-label {
  width: 40px;
  height: 9px;
  margin: var(--space-xs) auto 0;
}

.skeleton-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-sm);
}
.sk-stat-chip {
  height: 38px;
  border-radius: var(--radius-md);
}

.skeleton-page {
  padding: var(--space-md) 0;
}
.sk-page-title {
  width: 200px;
  height: 24px;
  margin-bottom: var(--space-md);
}
.sk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-md);
}
.sk-card-lg {
  height: 160px;
  border-radius: var(--radius-lg);
}
</style>
