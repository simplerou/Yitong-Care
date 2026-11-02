import { request } from './http'
import type { ChatTurn, LocalCitation, WebCitation, WebDiagnostics, WebSource } from './chat'
import type { SearchHit } from './retrieval'

export type DietCitation = LocalCitation | WebCitation
export type DietStatus = 'answered' | 'clarification' | 'insufficient' | 'emergency' | 'boundary'
export type DietSeverity = 'high' | 'moderate' | 'note'

export interface FoodMention {
  name: string
  canonical: string
  categories: string[]
  flags: string[]
  label: string
  note: string
  source: 'parsed' | 'provided'
}

export interface NutritionFinding {
  id: string
  severity: DietSeverity
  title: string
  foods: string[]
  detail: string
  action: string
}

export interface PortionItem { name: string; range_text: string; note: string }
export interface PortionReference { table_version: string; items: PortionItem[]; disclaimer: string }
export interface AdviceItem { kind: 'meal' | 'reason' | 'tip' | 'referral'; text: string; sources: number[] }
export interface DietAnswerChecks { status: 'passed' | 'partial' | 'blocked' | 'error'; checked_paragraphs: number; accepted_paragraphs: number; issues: string[] }
export interface DietMetrics {
  total_ms: number
  stage_ms: Record<string, number>
  llm_calls: number
  llm_failures: number
  llm_ms: number
  usage_calls: number
  prompt_tokens: number | null
  completion_tokens: number | null
}

export interface DietAnswer {
  status: DietStatus
  urgency: 'L1' | 'L2' | 'L3' | 'L4' | null
  required_action: string | null
  answer: string
  foods: FoodMention[]
  findings: NutritionFinding[]
  unknown_foods: string[]
  portion_reference: PortionReference | null
  nutrition_risks: string[]
  boundary: string | null
  advice: AdviceItem[]
  red_flags_observed: string[]
  triage_rule_ids: string[]
  missing_info: string[]
  route_suggestion: { agent: string; reason: string } | null
  coverage: 'complete' | 'partial' | 'none' | null
  missing_topics: string[]
  general_info: string[]
  dialogue_state: { conditions: string[]; allergies: string[]; chewing: string; swallowing: string; dislikes: string[]; foods_suggested: string[]; topic: string } | null
  citations: DietCitation[]
  retrieved_hits: SearchHit[]
  web_sources: WebSource[]
  web_status: 'not_used' | 'not_configured' | 'success' | 'no_results' | 'error'
  web_warning: string | null
  web_diagnostics: WebDiagnostics | null
  answer_checks: DietAnswerChecks | null
  metrics: DietMetrics | null
  disclaimer: string
  table_version: string
  vector_count: number
  reason: string | null
  retrieval_log_id: string | null
  model: string
  knowledge_scope: string[]
  steps: string[]
}

export interface DietConfig {
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

export interface DietFoodInput { name: string; amount?: string | null }

export const dietApi = {
  config: () => request<DietConfig>('/agents/diet/config'),
  ask: (question: string, history: ChatTurn[], signal?: AbortSignal) =>
    request<DietAnswer>('/agents/diet/chat', { method: 'POST', body: JSON.stringify({ question, history }), signal }, 600_000),
}

export interface DietConversationRecord { id: string; title: string; created_at: string; updated_at: string }
export interface DietStoredTurn {
  id: string
  conversation_id: string
  seq: number
  question: string
  status: 'running' | 'succeeded' | 'failed'
  stage?: string | null
  attempts: number
  response: DietAnswer | null
  error: string | null
  created_at: string
  updated_at: string
  transient?: boolean
}
export interface DietConversationDetail {
  conversation: DietConversationRecord
  turns: DietStoredTurn[]
  has_more: boolean
  next_before_seq: number | null
}

export const dietConversationsApi = {
  list: (page = 1) => request<{ items: DietConversationRecord[]; total: number; page: number; page_size: number }>(`/agents/diet/conversations?page=${page}`),
  create: () => request<DietConversationRecord>('/agents/diet/conversations', { method: 'POST' }),
  detail: (id: string, before?: number) =>
    request<DietConversationDetail>(`/agents/diet/conversations/${encodeURIComponent(id)}${before ? `?before_seq=${before}` : ''}`),
  remove: (id: string) => request<void>(`/agents/diet/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  ask: (id: string, requestId: string, question: string, retry = false, signal?: AbortSignal) =>
    request<DietStoredTurn>(`/agents/diet/conversations/${encodeURIComponent(id)}/turns`,
      { method: 'POST', body: JSON.stringify({ request_id: requestId, question, retry }), signal }, 600_000),
  progress: (id: string, requestId: string) =>
    request<{ request_id: string; status: string; stage: string | null }>(
      `/agents/diet/conversations/${encodeURIComponent(id)}/turns/${encodeURIComponent(requestId)}/progress`),
}
