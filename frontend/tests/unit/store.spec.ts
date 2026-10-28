import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDemoStore } from '../../src/stores/demo'
import { agents } from '../../src/config/agents'

beforeEach(() => {
  vi.stubGlobal('document', { documentElement: { classList: { toggle: vi.fn() } } })
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: vi.fn() })
  setActivePinia(createPinia())
  vi.useFakeTimers()
})
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('原型交互状态', () => {
  it('初始化为 8 份文档、17 个文本块，智能体只检索配置中的知识范围', () => {
    const store=useDemoStore()
    expect(store.state.docs).toHaveLength(8)
    expect(store.state.chunks).toHaveLength(17)
    const policy=agents.find(a=>a.id==='policy')!
    const hits=store.retrieve(policy.kbIds,'长期护理保险怎么申请',3,.02)
    expect(hits.length).toBeGreaterThan(0)
    expect(hits.every(h=>policy.kbIds.includes(h.chunk.docId))).toBe(true)
  })
  it('切块预览不修改已保存向量，保存后向量失效，重新入库后恢复', async () => {
    const store=useDemoStore(), doc=store.state.docs[0]
    const before=store.vectorCount
    store.state.chunkCfg.size=150
    expect(store.vectorCount).toBe(before)
    store.commitChunks(doc)
    expect(store.state.chunks.filter(c=>c.docId===doc.id).every(c=>!c.vectorized && c.vector===null)).toBe(true)
    expect(doc.status).toBe('chunked')
    store.state.vecCfg.docId=doc.id
    const task=store.vectorize()
    await vi.runAllTimersAsync();await task
    expect(doc.status).toBe('vectorized')
    expect(store.state.vectorProgress).toBe(100)
    expect(store.state.vectorBusy).toBe(false)
    expect(store.state.chunks.filter(c=>c.docId===doc.id).every(c=>c.vectorized)).toBe(true)
  })
  it('检索自动留痕，历史命中快照不随重新切块丢失', () => {
    const store=useDemoStore()
    store.search('跌倒后怎么处理')
    const snapshot=store.state.history[0]
    expect(snapshot.results.length).toBeGreaterThan(0)
    const oldText=snapshot.results[0].chunk.text
    const doc=store.state.docs.find(d=>d.id===snapshot.results[0].chunk.docId)!
    store.commitChunks(doc)
    expect(snapshot.results[0].chunk.text).toBe(oldText)
    expect(snapshot.results[0].chunk.vector).toBeNull()
  })
  it('问答流式完成后带引用，切换智能体不串话，清空只影响当前智能体', async () => {
    const store=useDemoStore(), health=agents[0],policy=agents[2]
    store.ensureChat(health);store.ensureChat(policy)
    const task=store.ask(health,'高血压老人每天吃多少盐？')
    expect(store.state.busy).toBe(true)
    await vi.runAllTimersAsync();await task
    const reply=store.state.chats.health.at(-1)!
    expect(reply.status).toBe('done')
    expect(reply.hits?.length).toBeGreaterThan(0)
    expect(reply.text).toContain('【1】')
    expect(store.state.chats.policy).toHaveLength(1)
    store.clearChat(health)
    expect(store.state.chats.health).toHaveLength(1)
    expect(store.state.chats.policy).toHaveLength(1)
    expect(store.state.lastHits.health).toHaveLength(0)
  })
  it('拒绝非法文件和超大文件，不生成文档', async () => {
    const store=useDemoStore()
    await store.upload(new File(['x'],'bad.exe'))
    expect(store.state.docs).toHaveLength(8)
    expect(store.toast?.type).toBe('error')
    await store.upload({name:'large.pdf',size:51*1024*1024} as File)
    expect(store.state.docs).toHaveLength(8)
    expect(store.toast?.text).toContain('50MB')
  })
})
