import { beforeEach,afterEach,expect,it,vi } from 'vitest'
import { createPinia,setActivePinia } from 'pinia'
import { retrievalApi,type SearchResult } from '../../src/api/retrieval'
import { useRetrievalStore } from '../../src/stores/retrieval'
vi.mock('../../src/api/retrieval',()=>({retrievalApi:{search:vi.fn(),logs:vi.fn(),replay:vi.fn(),remove:vi.fn(),clear:vi.fn()}}))
const result=(query='助餐'):SearchResult=>({log_id:'log1',query,scope:'all',top_k:5,threshold:.12,took_ms:12,vector_count:1,model:'real-model',hits:[],historical:false})
beforeEach(()=>{vi.stubGlobal('document',{documentElement:{classList:{toggle:vi.fn()}}});vi.stubGlobal('localStorage',{getItem:()=>null,setItem:vi.fn()});setActivePinia(createPinia());vi.clearAllMocks();vi.useFakeTimers();vi.mocked(retrievalApi.logs).mockResolvedValue({items:[],total:1,page:1,page_size:20})})
afterEach(()=>{vi.clearAllTimers();vi.useRealTimers();vi.unstubAllGlobals()})
it('服务失败时显示错误，不生成演示结果或本地检索记录',async()=>{
 vi.mocked(retrievalApi.search).mockRejectedValue(new Error('模型暂不可用'))
 const store=useRetrievalStore();await store.search('助餐')
 expect(store.result).toBeNull();expect(store.error).toBe('模型暂不可用');expect(store.records).toEqual([])
})
it('历史回放使用服务端快照，不重新调用向量模型',async()=>{
 vi.mocked(retrievalApi.replay).mockResolvedValue({...result(),historical:true})
 const store=useRetrievalStore();expect(await store.replay('log1')).toBe(true)
 expect(store.result?.historical).toBe(true);expect(store.parameters.query).toBe('助餐');expect(retrievalApi.search).not.toHaveBeenCalled()
})
it('较慢的旧查询不会覆盖后发的全局查询',async()=>{
 let resolve:(data:SearchResult)=>void=()=>{}
 vi.mocked(retrievalApi.search).mockReturnValueOnce(new Promise(r=>{resolve=r})).mockResolvedValueOnce(result('最新问题'))
 const store=useRetrievalStore(),old=store.search('旧问题');await store.search('最新问题');resolve(result('旧问题'));await old
 expect(store.result?.query).toBe('最新问题');expect(store.searching).toBe(false)
})
