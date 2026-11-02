import { request } from './http'
import type { ChatTurn, LocalCitation, WebCitation, WebDiagnostics, WebSource } from './chat'
import type { SearchHit } from './retrieval'

export type SafetyCitation = LocalCitation | WebCitation
export type SafetyStatus = 'answered' | 'clarification' | 'insufficient' | 'emergency' | 'boundary'
export type SafetySeverity = 'high' | 'moderate' | 'note'
export type RiskLevel = 'low' | 'medium' | 'high'

export interface HazardFinding { id: string; room: string; issue: string; severity: SafetySeverity; action: string; reference: string }
export interface RiskFactor { id: string; label: string; kind: 'history' | 'environment' | 'body' | 'medication' | 'living'; action: string }
export interface PostFallFinding { id: string; severity: SafetySeverity; title: string; detail: string; action: string }
export interface SafetyAdviceItem { kind: 'environment' | 'action' | 'reason' | 'referral'; text: string; sources: number[] }
export interface SafetyAnswerChecks { status: 'passed' | 'partial' | 'blocked' | 'error'; checked_paragraphs: number; accepted_paragraphs: number; issues: string[] }
export interface SafetyMetrics {
  total_ms: number
  stage_ms: Record<string, number>
  llm_calls: number
  llm_failures: number
  llm_ms: number
  usage_calls: number
  prompt_tokens: number | null
  completion_tokens: number | null
}

export interface SafetyAnswer {
  status: SafetyStatus
  urgency: 'L1' | 'L2' | 'L3' | 'L4' | null
  required_action: string | null
  answer: string
  hazards: HazardFinding[]
  risk_factors: RiskFactor[]
  risk_level: RiskLevel | null
  post_fall: PostFallFinding[]
  post_fall_advice: string | null
  boundary: string | null
  advice: SafetyAdviceItem[]
  red_flags_observed: string[]
  triage_rule_ids: string[]
  missing_info: string[]
  route_suggestion: { agent: string; reason: string } | null
  coverage: 'complete' | 'partial' | 'none' | null
  missing_topics: string[]
  general_info: string[]
  dialogue_state: { conditions: string[]; medications: string[]; previous_falls: number | null; living_alone: boolean | null; mobility: string; rooms: string[]; topic: string } | null
  citations: SafetyCitation[]
  retrieved_hits: SearchHit[]
  web_sources: WebSource[]
  web_status: 'not_used' | 'not_configured' | 'success' | 'no_results' | 'error'
  web_warning: string | null
  web_diagnostics: WebDiagnostics | null
  answer_checks: SafetyAnswerChecks | null
  metrics: SafetyMetrics | null
  disclaimer: string
  table_version: string
  vector_count: number
  reason: string | null
  retrieval_log_id: string | null
  model: string
  knowledge_scope: string[]
  steps: string[]
}

export interface SafetyConfig {
  model: string
  configured: boolean
  knowledge_scope: string[]
  web_configured: boolean
  workflow: string
  streaming: boolean
  enabled: boolean
  table_version: string
  disclaimer: string
  intents: string[]
}

export const safetyApi = {
  config: () => request<SafetyConfig>('/agents/safety/config'),
  ask: (question: string, history: ChatTurn[], signal?: AbortSignal) =>
    request<SafetyAnswer>('/agents/safety/chat', { method: 'POST', body: JSON.stringify({ question, history }), signal }, 600_000),
}

export interface SafetyConversationRecord { id: string; title: string; created_at: string; updated_at: string }
export interface SafetyStoredTurn {
  id: string
  conversation_id: string
  seq: number
  question: string
  status: 'running' | 'succeeded' | 'failed'
  stage?: string | null
  attempts: number
  response: SafetyAnswer | null
  error: string | null
  created_at: string
  updated_at: string
  transient?: boolean
}
export interface SafetyConversationDetail {
  conversation: SafetyConversationRecord
  turns: SafetyStoredTurn[]
  has_more: boolean
  next_before_seq: number | null
}

export const safetyConversationsApi = {
  list: (page = 1) => request<{ items: SafetyConversationRecord[]; total: number; page: number; page_size: number }>(`/agents/safety/conversations?page=${page}`),
  create: () => request<SafetyConversationRecord>('/agents/safety/conversations', { method: 'POST' }),
  detail: (id: string, before?: number) =>
    request<SafetyConversationDetail>(`/agents/safety/conversations/${encodeURIComponent(id)}${before ? `?before_seq=${before}` : ''}`),
  remove: (id: string) => request<void>(`/agents/safety/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  ask: (id: string, requestId: string, question: string, retry = false, signal?: AbortSignal) =>
    request<SafetyStoredTurn>(`/agents/safety/conversations/${encodeURIComponent(id)}/turns`,
      { method: 'POST', body: JSON.stringify({ request_id: requestId, question, retry }), signal }, 600_000),
  progress: (id: string, requestId: string) =>
    request<{ request_id: string; status: string; stage: string | null }>(
      `/agents/safety/conversations/${encodeURIComponent(id)}/turns/${encodeURIComponent(requestId)}/progress`),
}
