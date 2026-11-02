import { request } from './http'
import type { ChatTurn, LocalCitation, WebCitation, WebDiagnostics, WebSource } from './chat'
import type { SearchHit } from './retrieval'

export type MindCitation = LocalCitation | WebCitation
export type MindStatus = 'answered' | 'clarification' | 'insufficient' | 'crisis' | 'boundary'
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface RiskSignal { id: string; label: string; kind: 'risk' | 'protective' | 'trigger'; detail: string }
export interface ScreeningResult { low_mood: boolean; anhedonia: boolean; duration_two_weeks: boolean; functional_impairment: boolean; positive: boolean; note: string }
export interface MindAdviceItem { kind: 'empathy' | 'advice' | 'referral'; text: string; sources: number[] }
export interface MindAnswerChecks { status: 'passed' | 'partial' | 'blocked' | 'error'; checked_paragraphs: number; accepted_paragraphs: number; issues: string[] }
export interface MindMetrics {
  total_ms: number
  stage_ms: Record<string, number>
  llm_calls: number
  llm_failures: number
  llm_ms: number
  usage_calls: number
  prompt_tokens: number | null
  completion_tokens: number | null
}

export interface MindAnswer {
  status: MindStatus
  urgency: 'L1' | 'L2' | 'L3' | 'L4' | null
  required_action: string | null
  answer: string
  signals: RiskSignal[]
  screening: ScreeningResult | null
  risk_level: RiskLevel | null
  safety_plan: string[]
  crisis_notice: string | null
  boundary: string | null
  advice: MindAdviceItem[]
  red_flags_observed: string[]
  triage_rule_ids: string[]
  missing_info: string[]
  route_suggestion: { agent: string; reason: string } | null
  coverage: 'complete' | 'partial' | 'none' | null
  missing_topics: string[]
  general_info: string[]
  dialogue_state: { topic: string; mood_words: string[]; duration: string; sleep: string; support_person: string; losses: string[] } | null
  citations: MindCitation[]
  retrieved_hits: SearchHit[]
  web_sources: WebSource[]
  web_status: 'not_used' | 'not_configured' | 'success' | 'no_results' | 'error'
  web_warning: string | null
  web_diagnostics: WebDiagnostics | null
  answer_checks: MindAnswerChecks | null
  metrics: MindMetrics | null
  disclaimer: string
  table_version: string
  vector_count: number
  reason: string | null
  retrieval_log_id: string | null
  model: string
  knowledge_scope: string[]
  steps: string[]
}

export interface MindConfig {
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

export const mindApi = {
  config: () => request<MindConfig>('/agents/mind/config'),
  ask: (question: string, history: ChatTurn[], signal?: AbortSignal) =>
    request<MindAnswer>('/agents/mind/chat', { method: 'POST', body: JSON.stringify({ question, history }), signal }, 600_000),
}

export interface MindConversationRecord { id: string; title: string; created_at: string; updated_at: string }
export interface MindStoredTurn {
  id: string
  conversation_id: string
  seq: number
  question: string
  status: 'running' | 'succeeded' | 'failed'
  stage?: string | null
  attempts: number
  response: MindAnswer | null
  error: string | null
  created_at: string
  updated_at: string
  transient?: boolean
}
export interface MindConversationDetail {
  conversation: MindConversationRecord
  turns: MindStoredTurn[]
  has_more: boolean
  next_before_seq: number | null
}

export const mindConversationsApi = {
  list: (page = 1) => request<{ items: MindConversationRecord[]; total: number; page: number; page_size: number }>(`/agents/mind/conversations?page=${page}`),
  create: () => request<MindConversationRecord>('/agents/mind/conversations', { method: 'POST' }),
  detail: (id: string, before?: number) =>
    request<MindConversationDetail>(`/agents/mind/conversations/${encodeURIComponent(id)}${before ? `?before_seq=${before}` : ''}`),
  remove: (id: string) => request<void>(`/agents/mind/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  ask: (id: string, requestId: string, question: string, retry = false, signal?: AbortSignal) =>
    request<MindStoredTurn>(`/agents/mind/conversations/${encodeURIComponent(id)}/turns`,
      { method: 'POST', body: JSON.stringify({ request_id: requestId, question, retry }), signal }, 600_000),
  progress: (id: string, requestId: string) =>
    request<{ request_id: string; status: string; stage: string | null }>(
      `/agents/mind/conversations/${encodeURIComponent(id)}/turns/${encodeURIComponent(requestId)}/progress`),
}
