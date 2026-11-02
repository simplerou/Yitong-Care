import { beforeEach, expect, it, vi } from 'vitest'
import { request } from '../../src/api/http'
import { loadRecentConversations } from '../../src/api/home'
vi.mock('../../src/api/http', () => ({request:vi.fn()}))
beforeEach(() => vi.resetAllMocks())
it('从六个账号隔离的会话接口取最近记录并排序，不混入演示记录', async () => {
  vi.mocked(request).mockImplementation(async path => ({items:[{id:path,title:'当前账号会话',updated_at:path.includes('/health/')?'2026-11-02T10:00:00Z':'2026-11-01T10:00:00Z'}]}) as never)
  const result=await loadRecentConversations()
  expect(request).toHaveBeenCalledTimes(6)
  expect(result.items).toHaveLength(4)
  expect(result.items[0].agentId).toBe('health')
  expect(result.items.every(row => row.title==='当前账号会话')).toBe(true)
  expect(result.failed).toBe(0)
})
it('某个 Agent 的会话加载失败时保留其余结果并报告失败', async () => {
  vi.mocked(request).mockImplementation(async path => {if(path.includes('/policy/'))throw new Error('unavailable');return {items:[{id:path,title:'会话',updated_at:'2026-11-02T10:00:00Z'}]} as never})
  const result=await loadRecentConversations()
  expect(result.failed).toBe(1)
  expect(result.items).toHaveLength(4)
})
it('新账号没有会话时返回空列表', async () => {
  vi.mocked(request).mockResolvedValue({items:[]})
  expect(await loadRecentConversations()).toEqual({items:[],failed:0})
})
