import { beforeEach,afterEach,expect,it,vi } from 'vitest'
import { createPinia,setActivePinia } from 'pinia'
import { conversationsApi,type ConversationRecord,type ConversationDetail,type StoredTurn,type PolicyAnswer } from '../../src/api/chat'
import { ApiError } from '../../src/api/http'
import { usePolicyChatStore } from '../../src/stores/policyChat'
vi.mock('../../src/api/chat',()=>({conversationsApi:{list:vi.fn(),create:vi.fn(),detail:vi.fn(),remove:vi.fn(),ask:vi.fn()}}))
const conversation=(id='session-a'):ConversationRecord=>({id,title:'政策问答',created_at:'2026-10-29T00:00:00Z',updated_at:'2026-10-29T00:00:00Z'})
const answer=():PolicyAnswer=>({status:'answered',answer:'历史答案',citations:[],retrieved_hits:[],web_sources:[],web_status:'not_used',web_warning:null,vector_count:1,reason:'grounded_answer',retrieval_log_id:null,model:'saved-model',knowledge_scope:['general'],steps:[]})
const turn=(status:StoredTurn['status']='succeeded'):StoredTurn=>({id:'request-1',conversation_id:'session-a',seq:1,question:'问题',status,attempts:1,response:status==='succeeded'?answer():null,error:status==='failed'?'服务失败':null,created_at:'2026-10-29T00:00:00Z',updated_at:'2026-10-29T00:00:00Z'})
const detail=(turns:StoredTurn[]=[],id='session-a'):ConversationDetail=>({conversation:conversation(id),turns,has_more:false,next_before_seq:null})
let store:ReturnType<typeof usePolicyChatStore>
beforeEach(()=>{
 const saved=new Map<string,string>();vi.stubGlobal('localStorage',{getItem:(k:string)=>saved.get(k)||null,setItem:(k:string,v:string)=>saved.set(k,v),removeItem:(k:string)=>saved.delete(k)})
 vi.stubGlobal('crypto',{randomUUID:()=> 'request-1'});vi.useFakeTimers();setActivePinia(createPinia());vi.clearAllMocks()
 vi.mocked(conversationsApi.list).mockResolvedValue({items:[conversation()],total:1,page:1,page_size:20})
 vi.mocked(conversationsApi.create).mockResolvedValue(conversation());vi.mocked(conversationsApi.detail).mockResolvedValue(detail())
 store=usePolicyChatStore()
})
afterEach(()=>{store.stop();vi.clearAllTimers();vi.useRealTimers();vi.unstubAllGlobals()})
it('恢复服务端历史答案和快照，不调用问答接口',async()=>{
 localStorage.setItem('yitong-policy-conversation','session-a')
 vi.mocked(conversationsApi.detail).mockResolvedValue(detail([turn()]))
 await store.initialize()
 expect(store.latest?.answer).toBe('历史答案');expect(store.active?.id).toBe('session-a');expect(conversationsApi.ask).not.toHaveBeenCalled()
})
it('迟到的旧会话响应不会覆盖新选择',async()=>{
 let resolve:(data:ConversationDetail)=>void=()=>{}
 vi.mocked(conversationsApi.detail).mockReturnValueOnce(new Promise(r=>{resolve=r})).mockResolvedValueOnce(detail([], 'session-b'))
 const old=store.select('session-a');await store.select('session-b');resolve(detail());await old
 expect(store.active?.id).toBe('session-b')
})
it('网络结果不确定时，先核对服务器并重用同一个请求ID',async()=>{
 await store.select('session-a')
 vi.mocked(conversationsApi.ask).mockRejectedValueOnce(new ApiError('连接中断',0)).mockResolvedValueOnce(turn())
 vi.mocked(conversationsApi.detail).mockRejectedValueOnce(new ApiError('连接中断',0))
 await store.send('问题');expect(store.unconfirmed).toBe(true)
 vi.mocked(conversationsApi.detail).mockResolvedValueOnce(detail())
 await store.retry()
 expect(conversationsApi.ask).toHaveBeenCalledTimes(2)
 expect(vi.mocked(conversationsApi.ask).mock.calls.map(c=>c[1])).toEqual(['request-1','request-1'])
 expect(store.latest?.answer).toBe('历史答案');expect(store.unconfirmed).toBe(false)
})
it('超时后服务器已保存成功时直接回放，避免重复调用',async()=>{
 await store.select('session-a')
 vi.mocked(conversationsApi.ask).mockRejectedValueOnce(new ApiError('超时',0))
 vi.mocked(conversationsApi.detail).mockResolvedValueOnce(detail([turn()]))
 await store.send('问题')
 expect(store.latest?.answer).toBe('历史答案');expect(store.error).toBe('');expect(conversationsApi.ask).toHaveBeenCalledTimes(1)
})
it('服务端失败记录使用显式retry，保留原始请求标识',async()=>{
 await store.select('session-a')
 vi.mocked(conversationsApi.ask).mockRejectedValueOnce(new ApiError('服务失败',502)).mockResolvedValueOnce({...turn(),attempts:2})
 vi.mocked(conversationsApi.detail).mockResolvedValueOnce(detail([turn('failed')]))
 await store.send('问题');await store.retry()
 expect(vi.mocked(conversationsApi.ask).mock.calls[1]?.slice(0,4)).toEqual(['session-a','request-1','问题',true])
})
it('历史中的正在运行任务只轮询读取，不重复发送问题',async()=>{
 vi.mocked(conversationsApi.detail).mockResolvedValueOnce(detail([turn('running')])).mockResolvedValueOnce(detail([turn()]))
 await store.select('session-a');expect(store.pending).toBe(true)
 await vi.advanceTimersByTimeAsync(3000)
 expect(store.pending).toBe(false);expect(store.latest?.answer).toBe('历史答案');expect(conversationsApi.ask).not.toHaveBeenCalled()
})
it('轮询发现会话已被删除时停止，不无限请求旧会话',async()=>{
 vi.mocked(conversationsApi.detail).mockResolvedValueOnce(detail([turn('running')])).mockRejectedValueOnce(new ApiError('会话已删除',404))
 await store.select('session-a');await vi.advanceTimersByTimeAsync(3000)
 expect(store.active).toBeNull();expect(store.pending).toBe(false)
 const requests=vi.mocked(conversationsApi.detail).mock.calls.length
 await vi.advanceTimersByTimeAsync(9000)
 expect(conversationsApi.detail).toHaveBeenCalledTimes(requests)
})
