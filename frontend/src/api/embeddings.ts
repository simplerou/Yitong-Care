import { request } from './http'
export interface EmbeddingModel { id:string; name:string; dimensions:number; configured:boolean; hint:string }
export interface EmbeddingTask { id:number; doc_id:string; model:string; model_name:string; dimensions:number; batch_size:number; status:string; phase:string; progress:number; total:number; processed:number; log:string[]; error_message:string|null; index_version:number|null }
export interface IndexStatus { model:string; model_id:string; dimensions:number; index_type:string; vectors:number; documents:number; healthy:boolean; indexes:{ kb_id:string; kb_name:string; version:number; vectors:number; indexed_vectors:number; documents:number; healthy:boolean; status:string; message:string }[] }
export const embeddingsApi = {
  models: () => request<{models:EmbeddingModel[];batch_sizes:number[]}>('/embeddings/models'),
  status: () => request<IndexStatus>('/vector-index/status'),
  tasks: (docId?:string) => request<EmbeddingTask[]>(`/embeddings/tasks${docId ? '?doc_id='+encodeURIComponent(docId) : ''}`),
  task: (id:number) => request<EmbeddingTask>(`/embeddings/tasks/${id}`),
  create: (docId:string,model:string,batch:number) => request<EmbeddingTask>(`/documents/${encodeURIComponent(docId)}/embeddings`,{method:'POST',body:JSON.stringify({model,batch_size:batch})}),
  retry: (id:number) => request<EmbeddingTask>(`/embeddings/tasks/${id}/retry`,{method:'POST'}),
  rebuild: () => request<{rebuilt:{kb_id:string;version:number;vectors:number}[]}>('/vector-index/rebuild',{method:'POST',body:'{}'}),
}
