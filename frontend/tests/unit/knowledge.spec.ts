import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { documentsApi, type DocumentPage } from '../../src/api/documents'
import { useKnowledgeStore } from '../../src/stores/knowledge'

vi.mock('../../src/api/documents', () => ({ documentsApi: { list: vi.fn(), bases: vi.fn(), detail: vi.fn(), upload: vi.fn(), retry: vi.fn(), remove: vi.fn() } }))
const response = (name = '真实文档.txt'): DocumentPage => ({
  items: [{ id:'real-1', kb_id:'general', name, type:'TXT', size:300, source:'社区窗口', status:'parsed', error_message:null,
    chunk_count:0, vector_count:0, created_at:'2026-10-28T00:00:00+00:00', updated_at:'2026-10-28T00:00:00+00:00' }],
  total:1, page:1, page_size:20, stats:{ documents:1, chunks:0, vectors:0, pending:1 },
})
beforeEach(() => {
  vi.stubGlobal('document', { documentElement:{ classList:{ toggle:vi.fn() } } })
  vi.stubGlobal('localStorage', { getItem:()=>null, setItem:vi.fn() })
  vi.clearAllMocks(); setActivePinia(createPinia()); vi.useFakeTimers()
})
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('真实知识库状态', () => {
  it('后端失败时显示错误，不回退到 8 份演示文档', async () => {
    vi.mocked(documentsApi.list).mockRejectedValue(new Error('后端不可用'))
    const store = useKnowledgeStore(); await store.load()
    expect(store.error).toBe('后端不可用')
    expect(store.documents).toEqual([])
    expect(store.stats.documents).toBe(0)
  })
  it('从接口恢复真实文档及统计，新会话仍重新读取数据库', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(response())
    const store = useKnowledgeStore(); await store.load()
    expect(store.documents[0].persisted).toBe(true)
    expect(store.documents[0].name).toBe('真实文档.txt')
    expect(store.stats.documents).toBe(1)
    setActivePinia(createPinia())
    const newSession = useKnowledgeStore(); await newSession.load()
    expect(newSession.documents[0].id).toBe('real-1')
    expect(documentsApi.list).toHaveBeenCalledTimes(2)
  })
  it('较慢的旧查询结果不会覆盖最新筛选结果', async () => {
    let oldResult: (page: DocumentPage) => void = () => {}
    vi.mocked(documentsApi.list).mockReturnValueOnce(new Promise(resolve => { oldResult = resolve })).mockResolvedValueOnce(response('最新文档.txt'))
    const store = useKnowledgeStore(), older = store.load()
    store.query = '最新'; await store.load()
    oldResult(response('过期结果.txt')); await older
    expect(store.documents[0].name).toBe('最新文档.txt')
  })
  it('删除失败时保留列表，成功后才刷新并更新统计', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(response())
    const store = useKnowledgeStore(); await store.load()
    vi.mocked(documentsApi.remove).mockRejectedValueOnce(new Error('正在解析'))
    await store.remove('real-1')
    expect(store.documents).toHaveLength(1)
    vi.mocked(documentsApi.remove).mockResolvedValueOnce(undefined)
    vi.mocked(documentsApi.list).mockResolvedValueOnce({ ...response(), items:[], total:0, stats:{ documents:0, chunks:0, vectors:0, pending:0 } })
    await store.remove('real-1')
    expect(store.documents).toEqual([])
    expect(store.stats.documents).toBe(0)
  })
})
