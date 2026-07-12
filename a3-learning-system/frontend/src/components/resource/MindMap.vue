<!--
MindMap 思维导图组件 v2

将 Markdown 标题层级（# ## ### ####）解析为树结构，渲染为 SVG 横向树状图
修复：节点黑块、文字不可见、布局混乱、连线诡异等问题
配色统一为蓝白主题
-->
<template>
  <div class="mindmap-wrapper" :class="{ 'mm-fullscreen': isFullscreen }" :style="{ height: isFullscreen ? '100dvh' : height }">
    <!-- 工具栏 -->
    <div class="mm-toolbar" v-if="hasContent">
      <span class="mm-node-count">{{ nodeCount }} nodes</span>
      <el-button text size="small" @click="exportPng">导出PNG</el-button>
      <el-button text size="small" @click="toggleFullscreen">
        {{ isFullscreen ? '退出' : '全屏' }}
      </el-button>
    </div>

    <!-- 空状态 -->
    <div v-if="!hasContent" class="mm-empty">
      <svg viewBox="0 0 160 100" class="mm-empty-svg">
        <circle cx="80" cy="35" r="22" fill="none" :stroke="accentColor" stroke-width="2" stroke-dasharray="6 4"/>
        <circle cx="50" cy="72" r="14" fill="none" :stroke="greenColor" stroke-width="1.5" opacity="0.6"/>
        <circle cx="80" cy="78" r="14" fill="none" :stroke="purpleColor" stroke-width="1.5" opacity="0.6"/>
        <circle cx="110" cy="72" r="14" fill="none" :stroke="amberColor" stroke-width="1.5" opacity="0.6"/>
        <line x1="80" y1="57" x2="50" y2="62" :stroke="greenColor" stroke-width="1" opacity="0.4"/>
        <line x1="80" y1="57" x2="80" y2="66" :stroke="purpleColor" stroke-width="1" opacity="0.4"/>
        <line x1="80" y1="57" x2="110" y2="62" :stroke="amberColor" stroke-width="1" opacity="0.4"/>
      </svg>
      <p>暂无可渲染的思维导图</p>
    </div>

    <!-- SVG 画布 -->
    <div v-else ref="svgContainer" class="mm-svg-container">
      <svg :viewBox="viewBox" :width="svgSize.width" :height="svgSize.height" class="mm-svg" preserveAspectRatio="xMidYMin meet">
        <!-- 定义渐变和阴影 -->
        <defs>
          <linearGradient :id="'rootGrad-' + componentId" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#3B82F6" />
            <stop offset="100%" stop-color="#2563EB" />
          </linearGradient>
          <filter :id="'shadow-' + componentId" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#1E40AF" flood-opacity="0.15" />
          </filter>
        </defs>

        <!-- 连线（在节点下层） -->
        <g class="mm-edges">
          <path
            v-for="edge in edges"
            :key="edge.key"
            :d="edge.path"
            :stroke="edge.color"
            stroke-width="1.8"
            fill="none"
            stroke-linecap="round"
            class="mm-edge"
            opacity="0.6"
          />
        </g>

        <!-- 节点 -->
        <g
          v-for="node in layoutNodes"
          :key="node.id"
          class="mm-node-group"
          @mouseenter="hoveredNode = node.id"
          @mouseleave="hoveredNode = null"
        >
          <!-- 节点背景矩形 -->
          <rect
            :x="node.x - node.w / 2"
            :y="node.y - node.h / 2"
            :width="node.w"
            :height="node.h"
            :rx="node.level === 0 ? 10 : 8"
            :fill="nodeFill(node)"
            :stroke="node.color"
            :stroke-width="node.level === 0 ? 2.5 : 1.5"
            :style="{ filter: nodeFilter(node) }"
            class="mm-rect"
          />

          <!-- 节点文字 -->
          <text
            :x="node.x"
            :y="node.y + 1"
            text-anchor="middle"
            dominant-baseline="central"
            :fill="node.level === 0 || hoveredNode === node.id ? '#FFFFFF' : '#334155'"
            :font-size="node.level === 0 ? 14 : 12.5"
            :font-weight="node.level === 0 ? 700 : 500"
            class="mm-text"
          >{{ node.label }}</text>

          <!-- 子节点数量徽章 -->
          <g v-if="node.children.length > 0 && node.level < 2">
            <circle
              :cx="node.x + node.w / 2 - 6"
              :cy="node.y - node.h / 2 + 5"
              r="9"
              :fill="node.level === 0 ? '#FFFFFF' : node.color"
              opacity="0.9"
            />
            <text
              :x="node.x + node.w / 2 - 6"
              :y="node.y - node.h / 2 + 5.5"
              text-anchor="middle"
              :fill="node.level === 0 ? '#2563EB' : '#FFFFFF'"
              font-size="10"
              font-weight="600"
            >{{ node.children.length }}</text>
          </g>
        </g>
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { marked, type Token } from 'marked'
import { svgElementToPngDownload } from '@/utils/export'

const props = withDefaults(defineProps<{
  content: string
  height?: string
}>(), {
  height: '480px'
})

// 唯一ID用于SVG defs中的gradient/filter引用
const componentId = Math.random().toString(36).slice(2, 8)

// ═══ 蓝白主题配色 ═══
const levelColors = [
  '#2563EB',   // Level 0: 主蓝 — 根节点
  '#3B82F6',   // Level 1: 亮蓝 — 一级分支
  '#60A5FA',   // Level 2: 天蓝 — 二级分支
  '#93C5FD',   // Level 3: 浅蓝 — 三级分支
  '#BFDBFE',   // Level 4: 极浅蓝 — 叶节点
  '#DBEAFE',   // Level 5: 最浅蓝
]
const accentColor = '#2563EB'
const greenColor = '#0EA5E9'
const purpleColor = '#6366F1'
const amberColor = '#60A5FA'

// ═══ 状态 ═══
const isFullscreen = ref(false)
const hoveredNode = ref<string | null>(null)
const svgContainer = ref<HTMLElement | null>(null)

// ═══ 数据类型 ═══
interface MindMapNode {
  id: string
  label: string
  level: number
  children: MindMapNode[]
}

interface LayoutNode {
  id: string
  label: string
  level: number
  x: number
  y: number
  w: number   // 自适应宽度
  h: number
  color: string
  children: LayoutNode[]
}

interface Edge {
  key: string
  path: string
  color: string
}

// ═══ 文本宽度估算 ═══
function estimateTextWidth(text: string, fontSize: number): number {
  // 中文字符约等于 fontSize，英文约为 fontSize * 0.55
  let width = 0
  for (const ch of text) {
    if (/[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]/.test(ch)) {
      width += fontSize
    } else {
      width += fontSize * 0.58
    }
  }
  return Math.ceil(width) + 24  // 左右各12px padding
}

// ═══ 解析 Markdown 标题为树 ═══
function parseHeadings(md: string): MindMapNode | null {
  if (!md || !md.trim()) return null

  const tokens = marked.lexer(md)
  const headingTokens = tokens.filter((t: Token) => (t as { type: string }).type === 'heading')
  if (headingTokens.length === 0) return null

  const minDepth = Math.min(...headingTokens.map((t) => (t as { depth: number }).depth))
  const stack: { node: MindMapNode; depth: number }[] = []
  const dummyRoot: MindMapNode = { id: 'root', label: '', level: 0, children: [] }
  stack.push({ node: dummyRoot, depth: minDepth - 1 })

  headingTokens.forEach((t, i: number) => {
    const h = t as { text: string; depth: number }
    const label = (h.text || '').trim().slice(0, 30) || 'Untitled'
    const node: MindMapNode = {
      id: `n${i}`,
      label,
      level: h.depth - minDepth,
      children: []
    }
    while (stack.length > 0 && stack[stack.length - 1].depth >= h.depth) {
      stack.pop()
    }
    if (stack.length > 0) {
      stack[stack.length - 1].node.children.push(node)
    }
    stack.push({ node, depth: h.depth })
  })

  return dummyRoot.children.length > 0 ? dummyRoot.children[0] : null
}

// ═══ 布局算法 v2：自适应宽度 + 合理间距 ═══
function layoutTree(root: MindMapNode): { nodes: LayoutNode[]; edges: Edge[] } {
  const baseNodeH = 36           // 基础节点高度
  const levelGapX = 200          // 水平层级间距（加大避免拥挤）
  const nodeGapY = 20            // 垂直节点间距（加大）
  const paddingX = 60
  const paddingY = 40

  const nodes: LayoutNode[] = []
  const edges: Edge[] = []

  // 第一遍：叶子节点分配Y槽位
  let leafSlot = 0
  const leafMap = new Map<string, number>()

  function assignLeafSlots(node: MindMapNode) {
    if (node.children.length === 0) {
      leafMap.set(node.id, leafSlot++)
    }
    for (const child of node.children) {
      assignLeafSlots(child)
    }
  }
  assignLeafSlots(root)

  // 第二遍：自底向上计算坐标，自适应宽度
  function computePosition(node: MindMapNode): LayoutNode {
    const x = node.level * levelGapX + paddingX
    const fontSize = node.level === 0 ? 14 : 12.5
    const textW = estimateTextWidth(node.label, fontSize)
    // 根据层级调整最小/最大宽度
    const minW = node.level === 0 ? 120 : (node.level === 1 ? 100 : 80)
    const maxW = node.level === 0 ? 220 : 180
    const w = Math.max(minW, Math.min(maxW, textW))
    const h = baseNodeH

    let y: number

    if (node.children.length === 0) {
      // 叶子节点：使用预分配的槽位
      const slot = leafMap.get(node.id)!
      y = slot * (h + nodeGapY) + paddingY
    } else {
      // 非叶节点：子节点的Y中心
      const childLayouts = node.children.map(c => computePosition(c))
      const firstY = childLayouts[0].y
      const lastY = childLayouts[childLayouts.length - 1].y
      y = (firstY + lastY) / 2
    }

    const layoutNode: LayoutNode = {
      id: node.id,
      label: node.label,
      level: node.level,
      x,
      y,
      w,
      h,
      color: levelColors[Math.min(node.level, levelColors.length - 1)],
      children: []
    }

    // 递归处理子节点并生成连线
    for (const child of node.children) {
      const childLayout = computePosition(child)
      layoutNode.children.push(childLayout)
      nodes.push(childLayout)

      // 贝塞尔曲线连线 — 使用更自然的控制点
      const sx = x + w / 2
      const sy = y
      const ex = childLayout.x - childLayout.w / 2
      const ey = childLayout.y
      const dx = ex - sx
      const dy = ey - sy
      // 控制点距离取水平距离的40%，但有最小值保证曲线平滑
      const cpDist = Math.max(Math.abs(dx) * 0.42, 30)

      const path = `M ${sx} ${sy} C ${sx + cpDist} ${sy}, ${ex - cpDist} ${ey}, ${ex} ${ey}`
      edges.push({
        key: `${node.id}-${child.id}`,
        path,
        color: levelColors[Math.min(child.level + 1, levelColors.length - 1)],
      })
    }

    return layoutNode
  }

  const rootLayout = computePosition(root)
  nodes.unshift(rootLayout)  // 根节点放最前面（渲染在最上层）

  return { nodes, edges }
}

// ═══ 计算属性 ═══
const parsedRoot = computed(() => {
  try { return parseHeadings(props.content) } catch { return null }
})

const hasContent = computed(() => parsedRoot.value !== null)

const nodeCount = computed(() => {
  if (!parsedRoot.value) return 0
  function count(n: MindMapNode): number {
    return 1 + n.children.reduce((s, c) => s + count(c), 0)
  }
  return count(parsedRoot.value)
})

const layoutResult = computed(() => {
  if (!parsedRoot.value) return { nodes: [], edges: [] }
  return layoutTree(parsedRoot.value)
})

const layoutNodes = computed(() => layoutResult.value.nodes)
const edges = computed(() => layoutResult.value.edges)

const svgSize = computed(() => {
  if (!parsedRoot.value || layoutNodes.value.length === 0) {
    return { width: 900, height: 420 }
  }
  const maxLevel = Math.max(...layoutNodes.value.map(n => n.level))
  const maxY = Math.max(...layoutNodes.value.map(n => n.y))
  const minY = Math.min(...layoutNodes.value.map(n => n.y))

  const width = (maxLevel + 1) * 200 + 140
  const height = Math.max(maxY - minY + 140, 360)
  return { width, height }
})

const viewBox = computed(() => {
  const { width, height } = svgSize.value
  return `0 0 ${width} ${height}`
})

// ═══ 全屏切换 ═══
function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
  document.body.style.overflow = isFullscreen.value ? 'hidden' : ''
  nextTick(() => svgContainer.value?.scrollTo(0, 0))
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isFullscreen.value) toggleFullscreen()
}

function exportPng() {
  const svg = svgContainer.value?.querySelector('svg')
  if (!svg) return
  const title = parsedRoot.value?.label || 'mindmap'
  svgElementToPngDownload(svg, `${title}.png`)
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})

watch(() => props.content, () => { hoveredNode.value = null })

// ═══ 节点样式辅助函数 ═══
function nodeFill(node: LayoutNode): string {
  if (node.level === 0) return `url(#rootGrad-${componentId})`
  if (hoveredNode.value === node.id) return node.color
  return '#FFFFFF'
}

function nodeFilter(node: LayoutNode): string {
  if (node.level === 0) return `url(#shadow-${componentId})`
  if (hoveredNode.value === node.id) return `drop-shadow(0 3px 10px ${node.color}35)`
  return 'none'
}
</script>

<style scoped>
.mindmap-wrapper {
  position: relative;
  background: #FAFBFC;
  border: 1px solid #E2E8F0;
  border-radius: 14px;
  overflow: hidden;
  transition: all 0.35s ease;
}

.mm-toolbar {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 4px 14px;
  background: rgba(255,255,255,0.92);
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(15,23,42,0.06);
  backdrop-filter: blur(8px);
  font-size: 12px;
}

.mm-node-count {
  color: #94A3B8;
  font-size: 12px;
  font-weight: 500;
}

.mm-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 9999;
  border-radius: 0;
  border: none;
  background: #F8FAFC;
}

.mm-svg-container {
  width: 100%;
  height: 100%;
  overflow: auto;
  cursor: grab;
  padding: 16px 0;
}
.mm-svg-container:active { cursor: grabbing; }

.mm-svg {
  display: block;
  min-width: 100%;
  min-height: 100%;
}

/* ── 空状态 ── */
.mm-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 8px;
  color: #94A3B8;
}
.mm-empty p { font-size: 15px; font-weight: 600; margin-top: 8px; color: #64748B; }
.mm-empty-svg { width: 140px; height: 90px; opacity: 0.5; }

/* ── 连线动画 ── */
.mm-edge { transition: all 0.3s ease; }
.mm-node-group:hover ~ .mm-edges .mm-edge { opacity: 0.9; }

/* ── 节点交互 ── */
.mm-rect {
  cursor: pointer;
  transition: all 0.25s cubic-bezier(.22,.61,.36,1);
}
.mm-text {
  pointer-events: none;
  user-select: none;
  transition: fill 0.25s ease;
}
.mm-node-group:hover .mm-rect {
  transform-origin: center;
}
</style>
