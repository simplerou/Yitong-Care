import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { dietConversationsApi, type DietAnswer, type DietConversationDetail, type DietConversationRecord, type DietStoredTurn } from '../../src/api/diet'
import { ApiError } from '../../src/api/http'
import { useDietChatStore } from '../../src/stores/dietChat'

vi.mock('../../src/api/diet', () => ({
  dietConversationsApi: { list: vi.fn(), create: vi.fn(), detail: vi.fn(), remove: vi.fn(), ask: vi.fn(), progress: vi.fn() },
}))

const conversation = (id = 'diet-a'): DietConversationRecord => ({ id, title: '膳食问答', created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' })
const answer = (): DietAnswer => ({
  status: 'answered', urgency: 'L3', required_action: 'dietitian_referral', answer: '历史膳食回答',
  foods: [], findings: [], unknown_foods: [], portion_reference: null, nutrition_risks: [], boundary: null,
  advice: [], red_flags_observed: [], triage_rule_ids: [], missing_info: [], route_suggestion: null,
  coverage: 'complete', missing_topics: [], general_info: [], dialogue_state: null, citations: [], retrieved_hits: [],
  web_sources: [], web_status: 'not_used', web_warning: null, web_diagnostics: null, answer_checks: null, metrics: null,
  disclaimer: '不构成疾病治疗饮食处方', table_version: 'diet-ref-2022.1', vector_count: 1, reason: 'grounded_answer',
  retrieval_log_id: null, model: 'saved-model', knowledge_scope: ['general'], steps: [],
})
const turn = (status: DietStoredTurn['status'] = 'succeeded'): DietStoredTurn => ({
  id: 'request-1', conversation_id: 'diet-a', seq: 1, question: '高血压老人一日三餐怎么搭配', status, attempts: 1,
  response: status === 'succeeded' ? answer() : null, error: status === 'failed' ? '服务失败' : null,
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
})
const detail = (turns: DietStoredTurn[] = [], id = 'diet-a'): DietConversationDetail => ({ conversation: conversation(id), turns, has_more: false, next_before_seq: null })
let store: ReturnType<typeof useDietChatStore>

beforeEach(() => {
  const saved = new Map<string, string>()
  vi.stubGlobal('localStorage', { getItem: (k: string) => saved.get(k) || null, setItem: (k: string, v: string) => saved.set(k, v), removeItem: (k: string) => saved.delete(k) })
  vi.stubGlobal('crypto', { randomUUID: () => 'request-1' })
  vi.useFakeTimers(); setActivePinia(createPinia()); vi.clearAllMocks()
  vi.mocked(dietConversationsApi.list).mockResolvedValue({ items: [conversation()], total: 1, page: 1, page_size: 20 })
  vi.mocked(dietConversationsApi.create).mockResolvedValue(conversation())
  vi.mocked(dietConversationsApi.detail).mockResolvedValue(detail())
  store = useDietChatStore()
})
afterEach(() => { store.stop(); vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals() })

it('恢复保存的食物识别与回答，不调用问答接口', async () => {
  localStorage.setItem('yitong-diet-conversation', 'diet-a')
  vi.mocked(dietConversationsApi.detail).mockResolvedValue(detail([turn()]))
  await store.initialize()
  expect(store.latest?.answer).toBe('历史膳食回答')
  expect(store.latest?.urgency).toBe('L3')
  expect(store.active?.id).toBe('diet-a')
  expect(dietConversationsApi.ask).not.toHaveBeenCalled()
})

it('迟到的旧会话响应不会覆盖新选择', async () => {
  let resolve: (data: DietConversationDetail) => void = () => {}
  vi.mocked(dietConversationsApi.detail)
    .mockReturnValueOnce(new Promise(r => { resolve = r }))
    .mockResolvedValueOnce(detail([], 'diet-b'))
  const old = store.select('diet-a')
  await store.select('diet-b')
  resolve(detail())
  await old
  expect(store.active?.id).toBe('diet-b')
})

it('首次提问自动新建会话并使用同一请求标识处理不确定结果', async () => {
  vi.mocked(dietConversationsApi.ask).mockRejectedValueOnce(new ApiError('连接中断', 0)).mockResolvedValueOnce(turn())
  vi.mocked(dietConversationsApi.detail).mockRejectedValueOnce(new ApiError('连接中断', 0))
  await store.send('高血压老人一日三餐怎么搭配')
  expect(dietConversationsApi.create).toHaveBeenCalledTimes(1)
  expect(store.unconfirmed).toBe(true)
  vi.mocked(dietConversationsApi.detail).mockResolvedValueOnce(detail())
  await store.retry()
  expect(dietConversationsApi.ask).toHaveBeenCalledTimes(2)
  expect(vi.mocked(dietConversationsApi.ask).mock.calls.map(call => call[1])).toEqual(['request-1', 'request-1'])
  expect(store.unconfirmed).toBe(false)
})

it('正在运行的任务只轮询读取，不重复发送问题', async () => {
  vi.mocked(dietConversationsApi.detail).mockResolvedValueOnce(detail([turn('running')])).mockResolvedValueOnce(detail([turn()]))
  await store.select('diet-a')
  expect(store.pending).toBe(true)
  await vi.advanceTimersByTimeAsync(3000)
  expect(store.pending).toBe(false)
  expect(store.latest?.answer).toBe('历史膳食回答')
  expect(dietConversationsApi.ask).not.toHaveBeenCalled()
})

it('阶段轮询写入膳食节点名称', async () => {
  vi.mocked(dietConversationsApi.ask).mockImplementation(() => new Promise(() => {}))
  vi.mocked(dietConversationsApi.progress).mockResolvedValue({ request_id: 'request-1', status: 'running', stage: 'extract_foods' })
  await store.select('diet-a')
  void store.send('早上 150/95')
  await vi.advanceTimersByTimeAsync(1500)
  expect(store.stage).toBe('extract_foods')
})
