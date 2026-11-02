import { request } from './http'
import type { ChatTurn, LocalCitation, WebCitation, WebDiagnostics, WebSource } from './chat'
import type { SearchHit } from './retrieval'

export type MedicationCitation = LocalCitation | WebCitation
export type MedicationSeverity = 'high' | 'moderate' | 'note'
export type MedicationStatus = 'answered' | 'clarification' | 'insufficient' | 'emergency' | 'boundary'

export interface DrugMention {
  name: string
  canonical: string
  classes: string[]
  class_label: string
  tags: string[]
  indication: string
  timing_hint: string | null
  user_frequency: string
  source: 'parsed' | 'provided'
}

export interface InteractionFinding {
  id: string
  severity: MedicationSeverity
  title: string
  drugs: string[]
  detail: string
  action: string
}

export interface MedicationAnswerChecks {
  status: 'passed' | 'partial' | 'blocked' | 'error'
  checked_paragraphs: number
  accepted_paragraphs: number
  issues: string[]
}

export interface MedicationMetrics {
  total_ms: number
  stage_ms: Record<string, number>
  llm_calls: number
  llm_failures: number
  llm_ms: number
  usage_calls: number
  prompt_tokens: number | null
  completion_tokens: number | null
}

export interface MedicationAnswer {
  status: MedicationStatus
  urgency: 'L1' | 'L2' | 'L3' | 'L4' | null
  required_action: string | null
  answer: string
  drugs: DrugMention[]
  interactions: InteractionFinding[]
  unknown_names: string[]
  missed_dose_advice: string | null
  boundary: string | null
  red_flags_observed: string[]
  triage_rule_ids: string[]
  missing_info: string[]
  route_suggestion: { agent: string; reason: string } | null
  coverage: 'complete' | 'partial' | 'none' | null
  missing_topics: string[]
  general_info: string[]
  dialogue_state: { drugs: string[]; topic: string; frequency: string; symptoms: string[]; age: number | null; conditions: string[] } | null
  citations: MedicationCitation[]
  retrieved_hits: SearchHit[]
  web_sources: WebSource[]
  web_status: 'not_used' | 'not_configured' | 'success' | 'no_results' | 'error'
  web_warning: string | null
  web_diagnostics: WebDiagnostics | null
  answer_checks: MedicationAnswerChecks | null
  metrics: MedicationMetrics | null
  disclaimer: string
  table_version: string
  vector_count: number
  reason: string | null
  retrieval_log_id: string | null
  model: string
  knowledge_scope: string[]
  steps: string[]
}

export interface MedicationConfig {
  model: string
  configured: boolean
  knowledge_scope: string[]
  web_configured: boolean
  workflow: string
  streaming: boolean
  enabled: boolean
  table_version: string
  disclaimer: string
  topics: string[]
}

export interface MedicationInput { name: string; frequency?: string }

export const medicationApi = {
  config: () => request<MedicationConfig>('/agents/medication/config'),
  ask: (question: string, history: ChatTurn[], signal?: AbortSignal) =>
    request<MedicationAnswer>('/agents/medication/chat', { method: 'POST', body: JSON.stringify({ question, history }), signal }, 600_000),
}

export interface MedicationConversationRecord { id: string; title: string; created_at: string; updated_at: string }
export interface MedicationStoredTurn {
  id: string
  conversation_id: string
  seq: number
  question: string
  status: 'running' | 'succeeded' | 'failed'
  stage?: string | null
  attempts: number
  response: MedicationAnswer | null
  error: string | null
  created_at: string
  updated_at: string
  transient?: boolean
}
export interface MedicationConversationDetail {
  conversation: MedicationConversationRecord
  turns: MedicationStoredTurn[]
  has_more: boolean
  next_before_seq: number | null
}

export const medicationConversationsApi = {
  list: (page = 1) => request<{ items: MedicationConversationRecord[]; total: number; page: number; page_size: number }>(`/agents/medication/conversations?page=${page}`),
  create: () => request<MedicationConversationRecord>('/agents/medication/conversations', { method: 'POST' }),
  detail: (id: string, before?: number) =>
    request<MedicationConversationDetail>(`/agents/medication/conversations/${encodeURIComponent(id)}${before ? `?before_seq=${before}` : ''}`),
  remove: (id: string) => request<void>(`/agents/medication/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  ask: (id: string, requestId: string, question: string, retry = false, signal?: AbortSignal) =>
    request<MedicationStoredTurn>(`/agents/medication/conversations/${encodeURIComponent(id)}/turns`,
      { method: 'POST', body: JSON.stringify({ request_id: requestId, question, retry }), signal }, 600_000),
  progress: (id: string, requestId: string) =>
    request<{ request_id: string; status: string; stage: string | null }>(
      `/agents/medication/conversations/${encodeURIComponent(id)}/turns/${encodeURIComponent(requestId)}/progress`),
}
