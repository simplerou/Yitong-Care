import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { healthConversationsApi, type HealthAnswer, type HealthConversationDetail, type HealthConversationRecord, type HealthStoredTurn } from '../../src/api/health'
import { ApiError } from '../../src/api/http'
import { useHealthChatStore } from '../../src/stores/healthChat'

vi.mock('../../src/api/health', () => ({
  healthConversationsApi: { list: vi.fn(), create: vi.fn(), detail: vi.fn(), remove: vi.fn(), ask: vi.fn(), progress: vi.fn() },
}))

const conversation = (id = 'health-a'): HealthConversationRecord => ({ id, title: '健康问答', created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' })
const answer = (): HealthAnswer => ({
  status: 'answered', urgency: 'L3', required_action: 'clinic_visit', answer: '历史健康回答', vitals_assessment: null,
  red_flags_observed: [], missing_info: [], advice: [], triage_rule_ids: ['bp_stage1'], route_suggestion: null,
  coverage: 'complete', missing_topics: [], general_info: [], dialogue_state: null, citations: [], retrieved_hits: [],
  web_sources: [], web_status: 'not_used', web_warning: null, web_diagnostics: null, answer_checks: null, metrics: null,
  disclaimer: '不构成诊断或处方', table_version: 'cn-bp-2024', vector_count: 1, reason: 'grounded_answer',
  retrieval_log_id: null, model: 'saved-model', knowledge_scope: ['general'], steps: [],
})
const turn = (status: HealthStoredTurn['status'] = 'succeeded'): HealthStoredTurn => ({
  id: 'request-1', conversation_id: 'health-a', seq: 1, question: '早上 150/95 高吗', status, attempts: 1,
  response: status === 'succeeded' ? answer() : null, error: status === 'failed' ? '服务失败' : null,
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
})
const detail = (turns: HealthStoredTurn[] = [], id = 'health-a'): HealthConversationDetail => ({ conversation: conversation(id), turns, has_more: false, next_before_seq: null })
let store: ReturnType<typeof useHealthChatStore>

beforeEach(() => {
  const saved = new Map<string, string>()
  vi.stubGlobal('localStorage', { getItem: (k: string) => saved.get(k) || null, setItem: (k: string, v: string) => saved.set(k, v), removeItem: (k: string) => saved.delete(k) })
  vi.stubGlobal('crypto', { randomUUID: () => 'request-1' })
  vi.useFakeTimers(); setActivePinia(createPinia()); vi.clearAllMocks()
  vi.mocked(healthConversationsApi.list).mockResolvedValue({ items: [conversation()], total: 1, page: 1, page_size: 20 })
  vi.mocked(healthConversationsApi.create).mockResolvedValue(conversation())
  vi.mocked(healthConversationsApi.detail).mockResolvedValue(detail())
  store = useHealthChatStore()
})
afterEach(() => { store.stop(); vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals() })

it('恢复保存的指标判读与回答，不调用问答接口', async () => {
  localStorage.setItem('yitong-health-conversation', 'health-a')
  vi.mocked(healthConversationsApi.detail).mockResolvedValue(detail([turn()]))
  await store.initialize()
  expect(store.latest?.answer).toBe('历史健康回答')
  expect(store.latest?.urgency).toBe('L3')
  expect(store.active?.id).toBe('health-a')
  expect(healthConversationsApi.ask).not.toHaveBeenCalled()
})

it('迟到的旧会话响应不会覆盖新选择', async () => {
  let resolve: (data: HealthConversationDetail) => void = () => {}
  vi.mocked(healthConversationsApi.detail)
    .mockReturnValueOnce(new Promise(r => { resolve = r }))
    .mockResolvedValueOnce(detail([], 'health-b'))
  const old = store.select('health-a')
  await store.select('health-b')
  resolve(detail())
  await old
  expect(store.active?.id).toBe('health-b')
})

it('首次提问自动新建会话并使用同一请求标识处理不确定结果', async () => {
  vi.mocked(healthConversationsApi.ask).mockRejectedValueOnce(new ApiError('连接中断', 0)).mockResolvedValueOnce(turn())
  vi.mocked(healthConversationsApi.detail).mockRejectedValueOnce(new ApiError('连接中断', 0))
  await store.send('早上 150/95 高吗')
  expect(healthConversationsApi.create).toHaveBeenCalledTimes(1)
  expect(store.unconfirmed).toBe(true)
  vi.mocked(healthConversationsApi.detail).mockResolvedValueOnce(detail())
  await store.retry()
  expect(healthConversationsApi.ask).toHaveBeenCalledTimes(2)
  expect(vi.mocked(healthConversationsApi.ask).mock.calls.map(call => call[1])).toEqual(['request-1', 'request-1'])
  expect(store.unconfirmed).toBe(false)
})

it('正在运行的任务只轮询读取，不重复发送问题', async () => {
  vi.mocked(healthConversationsApi.detail).mockResolvedValueOnce(detail([turn('running')])).mockResolvedValueOnce(detail([turn()]))
  await store.select('health-a')
  expect(store.pending).toBe(true)
  await vi.advanceTimersByTimeAsync(3000)
  expect(store.pending).toBe(false)
  expect(store.latest?.answer).toBe('历史健康回答')
  expect(healthConversationsApi.ask).not.toHaveBeenCalled()
})

it('阶段轮询写入健康节点名称', async () => {
  vi.mocked(healthConversationsApi.ask).mockImplementation(() => new Promise(() => {}))
  vi.mocked(healthConversationsApi.progress).mockResolvedValue({ request_id: 'request-1', status: 'running', stage: 'assess_vitals' })
  await store.select('health-a')
  void store.send('早上 150/95')
  await vi.advanceTimersByTimeAsync(1500)
  expect(store.stage).toBe('assess_vitals')
})
