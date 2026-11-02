import { request } from './http'
import type { ChatTurn, LocalCitation, WebCitation, WebDiagnostics, WebSource } from './chat'
import type { SearchHit } from './retrieval'

export type HealthCitation = LocalCitation | WebCitation
export type Urgency = 'L1' | 'L2' | 'L3' | 'L4'
export type HealthStatus = 'answered' | 'clarification' | 'insufficient' | 'emergency'
export type VitalsCategoryCode =
  | 'normal' | 'elevated' | 'stage1' | 'stage2' | 'stage3' | 'crisis' | 'low' | 'severe_low'
  | 'high' | 'severe_high' | 'impaired' | 'diabetes_range' | 'igt' | 'low_fever' | 'moderate_fever'
  | 'high_fever' | 'hyperpyrexia' | 'hypothermia' | 'recorded' | 'unverified'

export interface VitalsReading {
  metric: string
  systolic: number | null
  diastolic: number | null
  value: number | null
  unit: string
  display: string
  context: 'home' | 'clinic' | 'unknown'
  condition: string
  category: string
  category_code: VitalsCategoryCode
  reference_basis: string
  table_version: string
  flags: string[]
  source: 'parsed' | 'provided'
}

export interface VitalsAssessment {
  readings: VitalsReading[]
  primary: VitalsReading | null
  missing: string[]
  implausible: boolean
  unverified_from_model: boolean
  table_version: string
}

export interface AdviceItem { kind: 'explain' | 'lifestyle' | 'monitor' | 'referral'; text: string; sources: number[] }
export interface RouteSuggestion { agent: 'medication' | 'policy' | 'safety' | 'diet' | 'mind'; reason: string }
export interface HealthDialogueState {
  metric: string
  value_text: string
  symptoms: string[]
  age: number | null
  conditions: string[]
  topic: string
  last_reading_keys: string[]
}
export interface HealthMetrics {
  total_ms: number
  stage_ms: Record<string, number>
  llm_calls: number
  llm_failures: number
  llm_ms: number
  usage_calls: number
  prompt_tokens: number | null
  completion_tokens: number | null
}
export interface HealthAnswerChecks {
  status: 'passed' | 'partial' | 'blocked' | 'error'
  checked_paragraphs: number
  accepted_paragraphs: number
  issues: string[]
  review_attempts?: number
}

export interface HealthAnswer {
  status: HealthStatus
  urgency: Urgency | null
  required_action: 'call_120' | 'emergency_department' | 'contact_doctor_24h' | 'clinic_visit' | 'self_care' | null
  answer: string
  vitals_assessment: VitalsAssessment | null
  red_flags_observed: string[]
  missing_info: string[]
  advice: AdviceItem[]
  triage_rule_ids: string[]
  route_suggestion: RouteSuggestion | null
  coverage: 'complete' | 'partial' | 'none' | null
  missing_topics: string[]
  general_info: string[]
  dialogue_state: HealthDialogueState | null
  citations: HealthCitation[]
  retrieved_hits: SearchHit[]
  web_sources: WebSource[]
  web_status: 'not_used' | 'not_configured' | 'success' | 'no_results' | 'error'
  web_warning: string | null
  web_diagnostics: WebDiagnostics | null
  answer_checks: HealthAnswerChecks | null
  metrics: HealthMetrics | null
  disclaimer: string
  table_version: string
  vector_count: number
  reason: string | null
  retrieval_log_id: string | null
  model: string
  knowledge_scope: string[]
  steps: string[]
}

export interface HealthConfig {
  model: string
  configured: boolean
  knowledge_scope: string[]
  web_configured: boolean
  workflow: string
  streaming: boolean
  enabled: boolean
  table_version: string
  disclaimer: string
  metrics: string[]
}

export interface HealthVitalsInput {
  metric: string
  systolic?: number | null
  diastolic?: number | null
  value?: number | null
  unit: string
  context?: 'home' | 'clinic' | 'unknown'
  condition?: string
}

export const healthApi = {
  config: () => request<HealthConfig>('/agents/health/config'),
  ask: (question: string, history: ChatTurn[], signal?: AbortSignal) =>
    request<HealthAnswer>('/agents/health/chat', { method: 'POST', body: JSON.stringify({ question, history }), signal }, 600_000),
}

export interface HealthConversationRecord { id: string; title: string; created_at: string; updated_at: string }
export interface HealthStoredTurn {
  id: string
  conversation_id: string
  seq: number
  question: string
  status: 'running' | 'succeeded' | 'failed'
  stage?: string | null
  attempts: number
  response: HealthAnswer | null
  error: string | null
  created_at: string
  updated_at: string
  transient?: boolean
}
export interface HealthConversationDetail {
  conversation: HealthConversationRecord
  turns: HealthStoredTurn[]
  has_more: boolean
  next_before_seq: number | null
}

export const healthConversationsApi = {
  list: (page = 1) => request<{ items: HealthConversationRecord[]; total: number; page: number; page_size: number }>(`/agents/health/conversations?page=${page}`),
  create: () => request<HealthConversationRecord>('/agents/health/conversations', { method: 'POST' }),
  detail: (id: string, before?: number) =>
    request<HealthConversationDetail>(`/agents/health/conversations/${encodeURIComponent(id)}${before ? `?before_seq=${before}` : ''}`),
  remove: (id: string) => request<void>(`/agents/health/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  ask: (id: string, requestId: string, question: string, retry = false, signal?: AbortSignal) =>
    request<HealthStoredTurn>(`/agents/health/conversations/${encodeURIComponent(id)}/turns`,
      { method: 'POST', body: JSON.stringify({ request_id: requestId, question, retry }), signal }, 600_000),
  progress: (id: string, requestId: string) =>
    request<{ request_id: string; status: string; stage: string | null }>(
      `/agents/health/conversations/${encodeURIComponent(id)}/turns/${encodeURIComponent(requestId)}/progress`),
}
