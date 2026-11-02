import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { safetyConversationsApi, type SafetyAnswer, type SafetyConversationDetail, type SafetyConversationRecord, type SafetyStoredTurn } from '../../src/api/safety'
import { ApiError } from '../../src/api/http'
import { useSafetyChatStore } from '../../src/stores/safetyChat'

vi.mock('../../src/api/safety', () => ({
  safetyConversationsApi: { list: vi.fn(), create: vi.fn(), detail: vi.fn(), remove: vi.fn(), ask: vi.fn(), progress: vi.fn() },
}))

const conversation = (id = 'safety-a'): SafetyConversationRecord => ({ id, title: '安全问答', created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' })
const answer = (): SafetyAnswer => ({
  status: 'answered', urgency: 'L4', required_action: 'self_care', answer: '历史安全回答',
  hazards: [], risk_factors: [], risk_level: 'low', post_fall: [], post_fall_advice: null, boundary: null,
  advice: [], red_flags_observed: [], triage_rule_ids: [], missing_info: [], route_suggestion: null,
  coverage: 'complete', missing_topics: [], general_info: [], dialogue_state: null, citations: [], retrieved_hits: [],
  web_sources: [], web_status: 'not_used', web_warning: null, web_diagnostics: null, answer_checks: null, metrics: null,
  disclaimer: '不构成医疗诊断', table_version: 'safety-home-2026.1', vector_count: 1, reason: 'grounded_answer',
  retrieval_log_id: null, model: 'saved-model', knowledge_scope: ['general'], steps: [],
})
const turn = (status: SafetyStoredTurn['status'] = 'succeeded'): SafetyStoredTurn => ({
  id: 'request-1', conversation_id: 'safety-a', seq: 1, question: '卫生间装扶手大概多高', status, attempts: 1,
  response: status === 'succeeded' ? answer() : null, error: status === 'failed' ? '服务失败' : null,
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
})
const detail = (turns: SafetyStoredTurn[] = [], id = 'safety-a'): SafetyConversationDetail => ({ conversation: conversation(id), turns, has_more: false, next_before_seq: null })
let store: ReturnType<typeof useSafetyChatStore>

beforeEach(() => {
  const saved = new Map<string, string>()
  vi.stubGlobal('localStorage', { getItem: (k: string) => saved.get(k) || null, setItem: (k: string, v: string) => saved.set(k, v), removeItem: (k: string) => saved.delete(k) })
  vi.stubGlobal('crypto', { randomUUID: () => 'request-1' })
  vi.useFakeTimers(); setActivePinia(createPinia()); vi.clearAllMocks()
  vi.mocked(safetyConversationsApi.list).mockResolvedValue({ items: [conversation()], total: 1, page: 1, page_size: 20 })
  vi.mocked(safetyConversationsApi.create).mockResolvedValue(conversation())
  vi.mocked(safetyConversationsApi.detail).mockResolvedValue(detail())
  store = useSafetyChatStore()
})
afterEach(() => { store.stop(); vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals() })

it('恢复保存的隐患识别与回答，不调用问答接口', async () => {
  localStorage.setItem('yitong-safety-conversation', 'safety-a')
  vi.mocked(safetyConversationsApi.detail).mockResolvedValue(detail([turn()]))
  await store.initialize()
  expect(store.latest?.answer).toBe('历史安全回答')
  expect(store.latest?.urgency).toBe('L4')
  expect(store.active?.id).toBe('safety-a')
  expect(safetyConversationsApi.ask).not.toHaveBeenCalled()
})

it('迟到的旧会话响应不会覆盖新选择', async () => {
  let resolve: (data: SafetyConversationDetail) => void = () => {}
  vi.mocked(safetyConversationsApi.detail)
    .mockReturnValueOnce(new Promise(r => { resolve = r }))
    .mockResolvedValueOnce(detail([], 'safety-b'))
  const old = store.select('safety-a')
  await store.select('safety-b')
  resolve(detail())
  await old
  expect(store.active?.id).toBe('safety-b')
})

it('首次提问自动新建会话并使用同一请求标识处理不确定结果', async () => {
  vi.mocked(safetyConversationsApi.ask).mockRejectedValueOnce(new ApiError('连接中断', 0)).mockResolvedValueOnce(turn())
  vi.mocked(safetyConversationsApi.detail).mockRejectedValueOnce(new ApiError('连接中断', 0))
  await store.send('卫生间装扶手大概多高')
  expect(safetyConversationsApi.create).toHaveBeenCalledTimes(1)
  expect(store.unconfirmed).toBe(true)
  vi.mocked(safetyConversationsApi.detail).mockResolvedValueOnce(detail())
  await store.retry()
  expect(safetyConversationsApi.ask).toHaveBeenCalledTimes(2)
  expect(vi.mocked(safetyConversationsApi.ask).mock.calls.map(call => call[1])).toEqual(['request-1', 'request-1'])
  expect(store.unconfirmed).toBe(false)
})

it('正在运行的任务只轮询读取，不重复发送问题', async () => {
  vi.mocked(safetyConversationsApi.detail).mockResolvedValueOnce(detail([turn('running')])).mockResolvedValueOnce(detail([turn()]))
  await store.select('safety-a')
  expect(store.pending).toBe(true)
  await vi.advanceTimersByTimeAsync(3000)
  expect(store.pending).toBe(false)
  expect(store.latest?.answer).toBe('历史安全回答')
  expect(safetyConversationsApi.ask).not.toHaveBeenCalled()
})

it('阶段轮询写入安全节点名称', async () => {
  vi.mocked(safetyConversationsApi.ask).mockImplementation(() => new Promise(() => {}))
  vi.mocked(safetyConversationsApi.progress).mockResolvedValue({ request_id: 'request-1', status: 'running', stage: 'extract_hazards' })
  await store.select('safety-a')
  void store.send('早上 150/95')
  await vi.advanceTimersByTimeAsync(1500)
  expect(store.stage).toBe('extract_hazards')
})
