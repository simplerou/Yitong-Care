import { request } from './http'
export interface SearchParameters { query:string; scope:string; top_k:number; threshold:number }
export interface SearchHit { chunk_id:number; doc_id:string; kb_id:string; doc_name:string; type:string; source:string; seq:number; start:number; end:number; chars:number; text:string; score:number; cos:number; lexical_score:number; bm25_score?:number|null; semantic_rank?:number|null; bm25_rank?:number|null }
export interface SearchResult extends SearchParameters { strategy?:string; log_id:string; took_ms:number; vector_count:number; model:string; hits:SearchHit[]; historical:boolean }
export interface RetrievalRecord { id:string; strategy?:string; query:string; scope:string; top_k:number; threshold:number; took_ms:number; hit_count:number; top_score:number|null; top_source:string|null; created_at:string }
export const retrievalApi = {
  search: (parameters:SearchParameters,signal?:AbortSignal) => request<SearchResult>('/retrieval/search',{method:'POST',body:JSON.stringify(parameters),signal}),
  logs: (page=1) => request<{items:RetrievalRecord[];total:number;page:number;page_size:number}>(`/retrieval/logs?page=${page}`),
  replay: (id:string) => request<SearchResult>(`/retrieval/logs/${encodeURIComponent(id)}`),
  remove: (id:string) => request<void>(`/retrieval/logs/${encodeURIComponent(id)}`,{method:'DELETE'}),
  clear: () => request<void>('/retrieval/logs',{method:'DELETE'}),
}
