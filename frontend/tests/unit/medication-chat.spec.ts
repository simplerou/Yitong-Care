import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { medicationConversationsApi, type MedicationAnswer, type MedicationConversationDetail, type MedicationConversationRecord, type MedicationStoredTurn } from '../../src/api/medication'
import { ApiError } from '../../src/api/http'
import { useMedicationChatStore } from '../../src/stores/medicationChat'

vi.mock('../../src/api/medication', () => ({
  medicationConversationsApi: { list: vi.fn(), create: vi.fn(), detail: vi.fn(), remove: vi.fn(), ask: vi.fn(), progress: vi.fn() },
}))

const conversation = (id = 'medication-a'): MedicationConversationRecord => ({ id, title: '用药问答', created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' })
const answer = (): MedicationAnswer => ({
  status: 'answered', urgency: 'L3', required_action: 'clinic_visit', answer: '历史用药回答', drugs: [], interactions: [], unknown_names: [], missed_dose_advice: null,
  boundary: null, red_flags_observed: [], triage_rule_ids: [], missing_info: [], route_suggestion: null,
  coverage: 'complete', missing_topics: [], general_info: [], dialogue_state: null, citations: [], retrieved_hits: [],
  web_sources: [], web_status: 'not_used', web_warning: null, web_diagnostics: null, answer_checks: null, metrics: null,
  disclaimer: '不构成处方', table_version: 'medication-rules-2026.1', vector_count: 1, reason: 'grounded_answer',
  retrieval_log_id: null, model: 'saved-model', knowledge_scope: ['general'], steps: [],
})
const turn = (status: MedicationStoredTurn['status'] = 'succeeded'): MedicationStoredTurn => ({
  id: 'request-1', conversation_id: 'medication-a', seq: 1, question: '华法林和阿司匹林一起吃要紧吗', status, attempts: 1,
  response: status === 'succeeded' ? answer() : null, error: status === 'failed' ? '服务失败' : null,
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
})
const detail = (turns: MedicationStoredTurn[] = [], id = 'medication-a'): MedicationConversationDetail => ({ conversation: conversation(id), turns, has_more: false, next_before_seq: null })
let store: ReturnType<typeof useMedicationChatStore>

beforeEach(() => {
  const saved = new Map<string, string>()
  vi.stubGlobal('localStorage', { getItem: (k: string) => saved.get(k) || null, setItem: (k: string, v: string) => saved.set(k, v), removeItem: (k: string) => saved.delete(k) })
  vi.stubGlobal('crypto', { randomUUID: () => 'request-1' })
  vi.useFakeTimers(); setActivePinia(createPinia()); vi.clearAllMocks()
  vi.mocked(medicationConversationsApi.list).mockResolvedValue({ items: [conversation()], total: 1, page: 1, page_size: 20 })
  vi.mocked(medicationConversationsApi.create).mockResolvedValue(conversation())
  vi.mocked(medicationConversationsApi.detail).mockResolvedValue(detail())
  store = useMedicationChatStore()
})
afterEach(() => { store.stop(); vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals() })

it('恢复保存的药物识别与回答，不调用问答接口', async () => {
  localStorage.setItem('yitong-medication-conversation', 'medication-a')
  vi.mocked(medicationConversationsApi.detail).mockResolvedValue(detail([turn()]))
  await store.initialize()
  expect(store.latest?.answer).toBe('历史用药回答')
  expect(store.latest?.urgency).toBe('L3')
  expect(store.active?.id).toBe('medication-a')
  expect(medicationConversationsApi.ask).not.toHaveBeenCalled()
})

it('迟到的旧会话响应不会覆盖新选择', async () => {
  let resolve: (data: MedicationConversationDetail) => void = () => {}
  vi.mocked(medicationConversationsApi.detail)
    .mockReturnValueOnce(new Promise(r => { resolve = r }))
    .mockResolvedValueOnce(detail([], 'medication-b'))
  const old = store.select('medication-a')
  await store.select('medication-b')
  resolve(detail())
  await old
  expect(store.active?.id).toBe('medication-b')
})

it('首次提问自动新建会话并使用同一请求标识处理不确定结果', async () => {
  vi.mocked(medicationConversationsApi.ask).mockRejectedValueOnce(new ApiError('连接中断', 0)).mockResolvedValueOnce(turn())
  vi.mocked(medicationConversationsApi.detail).mockRejectedValueOnce(new ApiError('连接中断', 0))
  await store.send('华法林和阿司匹林一起吃要紧吗')
  expect(medicationConversationsApi.create).toHaveBeenCalledTimes(1)
  expect(store.unconfirmed).toBe(true)
  vi.mocked(medicationConversationsApi.detail).mockResolvedValueOnce(detail())
  await store.retry()
  expect(medicationConversationsApi.ask).toHaveBeenCalledTimes(2)
  expect(vi.mocked(medicationConversationsApi.ask).mock.calls.map(call => call[1])).toEqual(['request-1', 'request-1'])
  expect(store.unconfirmed).toBe(false)
})

it('正在运行的任务只轮询读取，不重复发送问题', async () => {
  vi.mocked(medicationConversationsApi.detail).mockResolvedValueOnce(detail([turn('running')])).mockResolvedValueOnce(detail([turn()]))
  await store.select('medication-a')
  expect(store.pending).toBe(true)
  await vi.advanceTimersByTimeAsync(3000)
  expect(store.pending).toBe(false)
  expect(store.latest?.answer).toBe('历史用药回答')
  expect(medicationConversationsApi.ask).not.toHaveBeenCalled()
})

it('阶段轮询写入用药节点名称', async () => {
  vi.mocked(medicationConversationsApi.ask).mockImplementation(() => new Promise(() => {}))
  vi.mocked(medicationConversationsApi.progress).mockResolvedValue({ request_id: 'request-1', status: 'running', stage: 'extract_medications' })
  await store.select('medication-a')
  void store.send('早上 150/95')
  await vi.advanceTimersByTimeAsync(1500)
  expect(store.stage).toBe('extract_medications')
})
