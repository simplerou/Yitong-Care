import { request } from './http'
import type { SearchHit } from './retrieval'
export interface ChatTurn {role:'user'|'assistant';content:string}
export interface WebSource {search_scope?:'requested'|'city_fallback';search_query?:string|null;original_content_chars?:number|null;excerpt_start?:number|null;is_truncated?:boolean|null;coverage?:'excerpt'|'extracted_text';completeness_verified?:false;title:string;url:string;content:string;published_date:string|null;retrieved_at:string}
export interface LocalCitation {index:number;source_type?:'local';hit:SearchHit;web?:null}
export interface WebCitation {index:number;source_type:'web';web:WebSource;hit?:null}
export type PolicyCitation=LocalCitation|WebCitation
export function safeWebUrl(value:string){try{const url=new URL(value);return ['http:','https:'].includes(url.protocol)?url.href:null}catch{return null}}
export interface WebDiagnostics {attempts?:{query:string;stage:string;search_count:number;body_count:number;accepted_count:number;rejected_counts:Record<string,number>}[];search_query?:string|null;cache_hit?:boolean;stage:string;search_count:number;official_count:number;extraction_requested:number;extraction_returned:number;body_count:number;accepted_count:number;rejected_counts:Record<string,number>;pages:{search_query?:string|null;title:string;url:string;outcome:'accepted'|'rejected';reason:string}[]}
export interface ConsultationContext {region:string;age:number|null;household:string;benefit:string}
export interface PolicyDialogueState {region:string;district:string;household:string;age:number|null;benefit:string;aspect:string}
export interface PolicyAnswer {skill?:{name:string;version:string;sha256:string}|null;coverage?:'complete'|'partial'|'none'|null;missing_topics?:string[];general_info?:string[];dialogue_state?:PolicyDialogueState|null;consultation_context?:ConsultationContext|null;metrics?:{total_ms:number;stage_ms:Record<string,number>;llm_calls:number;llm_failures:number;llm_ms:number;usage_calls:number;prompt_tokens:number|null;completion_tokens:number|null}|null;answer_checks?:{status:'passed'|'partial'|'blocked'|'error';checked_paragraphs:number;accepted_paragraphs:number;issues:string[]}|null;policy_categories?:string[];web_diagnostics?:WebDiagnostics|null;status:'answered'|'clarification'|'insufficient';answer:string;citations:PolicyCitation[];retrieved_hits:SearchHit[];web_sources:WebSource[];web_status:'not_used'|'not_configured'|'success'|'no_results'|'error';web_warning:string|null;vector_count:number;reason:string|null;retrieval_log_id:string|null;model:string;knowledge_scope:string[];steps:string[]}
export const policyApi={
 config:()=>request<{model:string;configured:boolean;knowledge_scope:string[];web_configured:boolean}>('/agents/policy/config'),
 ask:(question:string,history:ChatTurn[],signal?:AbortSignal)=>request<PolicyAnswer>('/agents/policy/chat',{method:'POST',body:JSON.stringify({question,history}),signal},600_000),
}

export interface ConversationRecord {context?:ConsultationContext|null;id:string;title:string;created_at:string;updated_at:string}
export interface StoredTurn {stage?:string|null;id:string;conversation_id:string;seq:number;question:string;status:'running'|'succeeded'|'failed';attempts:number;response:PolicyAnswer|null;error:string|null;created_at:string;updated_at:string;transient?:boolean}
export interface ConversationDetail {conversation:ConversationRecord;turns:StoredTurn[];has_more:boolean;next_before_seq:number|null}
export const conversationsApi={
 saveContext:(id:string,context:ConsultationContext)=>request<ConversationRecord>(`/agents/policy/conversations/${encodeURIComponent(id)}/context`,{method:'PUT',body:JSON.stringify(context)}),
 progress:(id:string,requestId:string)=>request<{request_id:string;status:string;stage:string|null}>(`/agents/policy/conversations/${encodeURIComponent(id)}/turns/${encodeURIComponent(requestId)}/progress`),
 list:(page=1)=>request<{items:ConversationRecord[];total:number;page:number;page_size:number}>(`/agents/policy/conversations?page=${page}`),
 create:()=>request<ConversationRecord>('/agents/policy/conversations',{method:'POST'}),
 detail:(id:string,before?:number)=>request<ConversationDetail>(`/agents/policy/conversations/${encodeURIComponent(id)}${before?`?before_seq=${before}`:''}`),
 remove:(id:string)=>request<void>(`/agents/policy/conversations/${encodeURIComponent(id)}`,{method:'DELETE'}),
 ask:(id:string,requestId:string,question:string,retry=false,signal?:AbortSignal)=>request<StoredTurn>(`/agents/policy/conversations/${encodeURIComponent(id)}/turns`,{method:'POST',body:JSON.stringify({request_id:requestId,question,retry}),signal},600_000),
}
