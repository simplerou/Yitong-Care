import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { embeddingsApi, type EmbeddingModel, type EmbeddingTask, type IndexStatus } from '../api/embeddings'
import { useKnowledgeStore } from './knowledge'
import { useDemoStore } from './demo'
export const useVectorStore = defineStore('vectors',()=>{
  const models=ref<EmbeddingModel[]>([]),status=ref<IndexStatus|null>(null),task=ref<EmbeddingTask|null>(null)
  const error=ref(''),busy=ref(false),rebuilding=ref(false),batch=ref(16)
  const knowledge=useKnowledgeStore(),toast=useDemoStore()
  const active=computed(()=>!!task.value && ['queued','running'].includes(task.value.status))
  async function load() {
    try { const [m,s]=await Promise.all([embeddingsApi.models(),embeddingsApi.status()]);models.value=m.models;status.value=s;error.value='' }
    catch(e){error.value=e instanceof Error?e.message:'加载向量信息失败。'}
  }
  async function latest(docId:string) {
    try {const rows=await embeddingsApi.tasks(docId);if(knowledge.selectedDocId===docId)task.value=rows[0]||null}
    catch(e){error.value=e instanceof Error?e.message:'任务加载失败。'}
  }
  async function refresh() {
    const id=task.value?.id
    if(!id)return
    try {
      const result=await embeddingsApi.task(id)
      if(task.value?.id!==id)return
      const wasActive=active.value;task.value=result;error.value=''
      if(wasActive&&!active.value){
        await Promise.allSettled([load(),knowledge.load(),knowledge.loadChoices()])
        toast.notify(result.status==='succeeded'?'向量入库完成。':result.error_message||'向量任务失败，可重试。',result.status==='succeeded'?'success':'error')
      }
    }catch(e){error.value=e instanceof Error?e.message:'任务刷新失败。'}
  }
  async function start() {
    if(busy.value||active.value||!models.value[0]?.configured)return
    busy.value=true
    try {task.value=await embeddingsApi.create(knowledge.selectedDocId,models.value[0].id,batch.value);const doc=knowledge.choices.find(d=>d.id===knowledge.selectedDocId);if(doc){doc.status='vectorizing';doc.vectorCount=0}error.value='';toast.notify('向量任务已创建。')}
    catch(e){toast.notify(e instanceof Error?e.message:'创建任务失败。','error')}
    finally{busy.value=false}
  }
  async function retry() {
    if(!task.value||busy.value)return
    busy.value=true
    try{task.value=await embeddingsApi.retry(task.value.id);error.value='';toast.notify('已提交任务恢复请求。')}
    catch(e){toast.notify(e instanceof Error?e.message:'重试失败。','error')}
    finally{busy.value=false}
  }
  async function rebuild() {
    if(rebuilding.value||active.value)return
    rebuilding.value=true
    try{await embeddingsApi.rebuild();await load();toast.notify('索引已从数据库重建。')}
    catch(e){toast.notify(e instanceof Error?e.message:'重建失败。','error')}
    finally{rebuilding.value=false}
  }
  return{models,status,task,error,busy,rebuilding,batch,active,load,latest,refresh,start,retry,rebuild}
})
