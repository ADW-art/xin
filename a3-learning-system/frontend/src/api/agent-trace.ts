/*
Agent Trace API 模块

作用：
  封装多智能体调用链追踪相关的后端接口调用

关联文件：
  views/AgentCenter.vue
*/
import api from './index'

export interface TraceNode {
  agent: string
  display_name: string
  icon: string
  duration_ms: number
  input_tokens: number
  output_tokens: number
  intent?: string
  input_preview: string
  output_preview: string
  error?: string
}

export interface TraceEdge {
  source: string
  target: string
  relation: string
}

export interface TraceSummary {
  total_tokens: number
  total_duration_ms: number
  agent_count: number
  llm_calls: number
}

export interface TraceResponse {
  thread_id: string
  agents_used: string[]
  call_chain: TraceNode[]
  edges: TraceEdge[]
  summary: TraceSummary | null
}

export interface AgentManifestItem {
  name: string
  displayName: string
  description: string
  icon: string
  category: string
  terminal: boolean
  keywords: string[]
}

export function getLatestTrace(threadId?: string) {
  return api.get<TraceResponse>('/agent-trace/latest', {
    params: threadId ? { thread_id: threadId } : {},
  })
}

export function getAgentManifest() {
  return api.get<AgentManifestItem[]>('/agent-trace/manifest')
}
