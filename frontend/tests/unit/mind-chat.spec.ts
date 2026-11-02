import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mindConversationsApi, type MindAnswer, type MindConversationDetail, type MindConversationRecord, type MindStoredTurn } from '../../src/api/mind'
import { ApiError } from '../../src/api/http'
import { useMindChatStore } from '../../src/stores/mindChat'

vi.mock('../../src/api/mind', () => ({
  mindConversationsApi: { list: vi.fn(), create: vi.fn(), detail: vi.fn(), remove: vi.fn(), ask: vi.fn(), progress: vi.fn() },
}))

const conversation = (id = 'mind-a'): MindConversationRecord => ({ id, title: '心理陪伴', created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' })
const answer = (): MindAnswer => ({
  status: 'answered', urgency: 'L3', required_action: 'self_care', answer: '历史陪伴回答',
  signals: [], screening: null, risk_level: 'low', safety_plan: [], crisis_notice: null, boundary: null,
  advice: [], red_flags_observed: [], triage_rule_ids: [], missing_info: [], route_suggestion: null,
  coverage: 'complete', missing_topics: [], general_info: [], dialogue_state: null, citations: [], retrieved_hits: [],
  web_sources: [], web_status: 'not_used', web_warning: null, web_diagnostics: null, answer_checks: null, metrics: null,
  disclaimer: '不构成诊断', table_version: 'mind-screen-2026.1', vector_count: 1, reason: 'grounded_answer',
  retrieval_log_id: null, model: 'saved-model', knowledge_scope: ['general'], steps: [],
})
const turn = (status: MindStoredTurn['status'] = 'succeeded'): MindStoredTurn => ({
  id: 'request-1', conversation_id: 'mind-a', seq: 1, question: '老伴走了以后，一直高兴不起来', status, attempts: 1,
  response: status === 'succeeded' ? answer() : null, error: status === 'failed' ? '服务失败' : null,
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
})
const detail = (turns: MindStoredTurn[] = [], id = 'mind-a'): MindConversationDetail => ({ conversation: conversation(id), turns, has_more: false, next_before_seq: null })
let store: ReturnType<typeof useMindChatStore>

beforeEach(() => {
  const saved = new Map<string, string>()
  vi.stubGlobal('localStorage', { getItem: (k: string) => saved.get(k) || null, setItem: (k: string, v: string) => saved.set(k, v), removeItem: (k: string) => saved.delete(k) })
  vi.stubGlobal('crypto', { randomUUID: () => 'request-1' })
  vi.useFakeTimers(); setActivePinia(createPinia()); vi.clearAllMocks()
  vi.mocked(mindConversationsApi.list).mockResolvedValue({ items: [conversation()], total: 1, page: 1, page_size: 20 })
  vi.mocked(mindConversationsApi.create).mockResolvedValue(conversation())
  vi.mocked(mindConversationsApi.detail).mockResolvedValue(detail())
  store = useMindChatStore()
})
afterEach(() => { store.stop(); vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals() })

it('恢复保存的情绪线索与回答，不调用问答接口', async () => {
  localStorage.setItem('yitong-mind-conversation', 'mind-a')
  vi.mocked(mindConversationsApi.detail).mockResolvedValue(detail([turn()]))
  await store.initialize()
  expect(store.latest?.answer).toBe('历史陪伴回答')
  expect(store.latest?.urgency).toBe('L3')
  expect(store.active?.id).toBe('mind-a')
  expect(mindConversationsApi.ask).not.toHaveBeenCalled()
})

it('迟到的旧会话响应不会覆盖新选择', async () => {
  let resolve: (data: MindConversationDetail) => void = () => {}
  vi.mocked(mindConversationsApi.detail)
    .mockReturnValueOnce(new Promise(r => { resolve = r }))
    .mockResolvedValueOnce(detail([], 'mind-b'))
  const old = store.select('mind-a')
  await store.select('mind-b')
  resolve(detail())
  await old
  expect(store.active?.id).toBe('mind-b')
})

it('首次提问自动新建会话并使用同一请求标识处理不确定结果', async () => {
  vi.mocked(mindConversationsApi.ask).mockRejectedValueOnce(new ApiError('连接中断', 0)).mockResolvedValueOnce(turn())
  vi.mocked(mindConversationsApi.detail).mockRejectedValueOnce(new ApiError('连接中断', 0))
  await store.send('老伴走了以后，一直高兴不起来')
  expect(mindConversationsApi.create).toHaveBeenCalledTimes(1)
  expect(store.unconfirmed).toBe(true)
  vi.mocked(mindConversationsApi.detail).mockResolvedValueOnce(detail())
  await store.retry()
  expect(mindConversationsApi.ask).toHaveBeenCalledTimes(2)
  expect(vi.mocked(mindConversationsApi.ask).mock.calls.map(call => call[1])).toEqual(['request-1', 'request-1'])
  expect(store.unconfirmed).toBe(false)
})

it('正在运行的任务只轮询读取，不重复发送问题', async () => {
  vi.mocked(mindConversationsApi.detail).mockResolvedValueOnce(detail([turn('running')])).mockResolvedValueOnce(detail([turn()]))
  await store.select('mind-a')
  expect(store.pending).toBe(true)
  await vi.advanceTimersByTimeAsync(3000)
  expect(store.pending).toBe(false)
  expect(store.latest?.answer).toBe('历史陪伴回答')
  expect(mindConversationsApi.ask).not.toHaveBeenCalled()
})

it('阶段轮询写入陪伴节点名称', async () => {
  vi.mocked(mindConversationsApi.ask).mockImplementation(() => new Promise(() => {}))
  vi.mocked(mindConversationsApi.progress).mockResolvedValue({ request_id: 'request-1', status: 'running', stage: 'assess_mind' })
  await store.select('mind-a')
  void store.send('早上 150/95')
  await vi.advanceTimersByTimeAsync(1500)
  expect(store.stage).toBe('assess_mind')
})
