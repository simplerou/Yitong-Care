import { reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { retrievalApi, type SearchResult, type RetrievalRecord } from '../api/retrieval'
import { useDemoStore } from './demo'
export const useRetrievalStore=defineStore('retrieval',()=>{
  const parameters=reactive({query:'',scope:'all',top_k:5,threshold:.12})
  const result=ref<SearchResult|null>(null),records=ref<RetrievalRecord[]>([]),total=ref(0),page=ref(1)
  const searching=ref(false),loading=ref(false),error=ref(''),logsError=ref(''),busyId=ref('')
  const toast=useDemoStore()
  let searchGeneration=0, controller:AbortController|undefined
  async function search(query=parameters.query){
    if(!query.trim()){toast.notify('请输入检索内容。','warn');return}
    controller?.abort();controller=new AbortController();const signal=controller.signal,current=++searchGeneration
    parameters.query=query.trim();searching.value=true;error.value='';result.value=null
    try{const data=await retrievalApi.search({...parameters},signal);if(current!==searchGeneration)return;result.value=data;void loadLogs();toast.notify(result.value.hits.length?`检索完成，命中 ${result.value.hits.length} 条片段。`:'未命中，请降低阈值或扩大范围。',result.value.hits.length?'success':'warn')}
    catch(e){if(current===searchGeneration&&!signal.aborted)error.value=e instanceof Error?e.message:'检索失败。'}
    finally{if(current===searchGeneration)searching.value=false}
  }
  async function loadLogs(){
    loading.value=true
    try{const data=await retrievalApi.logs(page.value);records.value=data.items;total.value=data.total;logsError.value=''}
    catch(e){logsError.value=e instanceof Error?e.message:'检索记录加载失败。'}
    finally{loading.value=false}
  }
  async function replay(id:string){
    if(busyId.value)return false
    busyId.value=id
    try{const data=await retrievalApi.replay(id);result.value=data;Object.assign(parameters,{query:data.query,scope:data.scope,top_k:data.top_k,threshold:data.threshold});error.value='';return true}
    catch(e){toast.notify(e instanceof Error?e.message:'回放失败。','error');return false}
    finally{busyId.value=''}
  }
  async function remove(id?:string){
    if(busyId.value)return
    busyId.value=id||'all'
    try{if(id)await retrievalApi.remove(id);else await retrievalApi.clear();if(records.value.length===1&&page.value>1)page.value--;await loadLogs();toast.notify('检索记录已删除。')}
    catch(e){toast.notify(e instanceof Error?e.message:'删除失败。','error')}
    finally{busyId.value=''}
  }
  return{parameters,result,records,total,page,searching,loading,error,logsError,busyId,search,loadLogs,replay,remove}
})
