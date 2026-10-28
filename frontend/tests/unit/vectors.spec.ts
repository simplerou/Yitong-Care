import {beforeEach,afterEach,expect,it,vi} from 'vitest'
import {createPinia,setActivePinia} from 'pinia'
import {embeddingsApi,type EmbeddingTask} from '../../src/api/embeddings'
import {useVectorStore} from '../../src/stores/vectors'
vi.mock('../../src/api/embeddings',()=>({embeddingsApi:{models:vi.fn(),status:vi.fn(),tasks:vi.fn(),task:vi.fn(),create:vi.fn(),retry:vi.fn(),rebuild:vi.fn()}}))
const task=(id:number):EmbeddingTask=>({id,doc_id:'doc1',model:'model-key',model_name:'model',dimensions:1024,batch_size:16,status:'running',phase:'embedding',progress:50,total:10,processed:5,log:[],error_message:null,index_version:null})
beforeEach(()=>{vi.stubGlobal('document',{documentElement:{classList:{toggle:vi.fn()}}});vi.stubGlobal('localStorage',{getItem:()=>null,setItem:vi.fn()});setActivePinia(createPinia());vi.clearAllMocks();vi.useFakeTimers()})
afterEach(()=>{vi.clearAllTimers();vi.useRealTimers();vi.unstubAllGlobals()})
it('模型未配置时不发起向量任务',async()=>{const store=useVectorStore();store.models=[{id:'model-key',name:'model',dimensions:1024,configured:false,hint:'需要配置'}];await store.start();expect(embeddingsApi.create).not.toHaveBeenCalled()})
it('旧任务的迟到轮询不会覆盖新任务',async()=>{
 let resolve:(value:EmbeddingTask)=>void=()=>{}
 vi.mocked(embeddingsApi.task).mockReturnValueOnce(new Promise(r=>{resolve=r}))
 const store=useVectorStore();store.task=task(1);const refresh=store.refresh();store.task=task(2);resolve({...task(1),status:'succeeded',progress:100});await refresh
 expect(store.task.id).toBe(2);expect(store.task.progress).toBe(50)
})
