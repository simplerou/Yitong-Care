import { request } from './http'
export interface Identity {account_id:string;name:string;role:string;role_name:string;qualified:boolean;tools:string[];tasks:string[];roles:Record<string,string>}
export interface Draft {resident_name?:string|null;calculation?:Record<string,any>;id:string;kind:string;status:string;risk:number;version:number;proposed:Record<string,any>;current:Record<string,any>;validation:Record<string,any>;trace:Record<string,any>[];expires_at:string;decision_note:string;can_approve:boolean;can_edit:boolean;owner_id:string;created_at:string}
export const ops={
 identity:()=>request<Identity>('/operations/identity'),
 list:<T=any>(resource:string)=>request<{items:T[]}>(`/operations/${resource}`),
 get:<T=any>(path:string)=>request<T>(`/operations/${path}`),
 post:<T=any>(path:string,data:unknown={})=>request<T>(`/operations/${path}`,{method:'POST',body:JSON.stringify(data)},180000),
 put:<T=any>(path:string,data:unknown)=>request<T>(`/operations/${path}`,{method:'PUT',body:JSON.stringify(data)},180000),
 run:(task:string,payload:unknown,use_model:boolean,instruction='')=>ops.post<Draft>('run',{task,payload,use_model,instruction}),
}
