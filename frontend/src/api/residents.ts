import { request } from './http'
export interface ResidentInput {
  name:string; gender:string; birth_date:string|null; admission_date:string|null; status:string; location:string; care_level:string;
  contact_name:string; contact_relation:string; contact_phone:string; allergies:string; chronic_conditions:string; dietary_notes:string;
  mobility_notes:string; communication_notes:string; care_notes:string; source:string; assigned_account_ids:string[];
}
export interface Resident extends ResidentInput {id:string;record_no:string;version:number;created_at:string;updated_at:string}
export type ResidentSummary = Pick<Resident,'id'|'record_no'|'name'|'gender'|'birth_date'|'location'|'care_level'|'status'|'updated_at'>
export interface ResidentChange {id:string;actor_name:string;reason:string;created_at:string;before:Resident|null;after:Resident}
export const emptyResident = ():ResidentInput => ({name:'',gender:'unknown',birth_date:null,admission_date:null,status:'in_care',location:'',care_level:'未评估',contact_name:'',contact_relation:'',contact_phone:'',allergies:'',chronic_conditions:'',dietary_notes:'',mobility_notes:'',communication_notes:'',care_notes:'',source:'',assigned_account_ids:[]})
export const residentsApi = {
  list:(q='',status='',page=1)=>request<{items:ResidentSummary[];total:number;page:number;page_size:number}>(`/residents?${new URLSearchParams({q,page:String(page),...(status?{status}:{})})}`),
  detail:(id:string)=>request<Resident>(`/residents/${encodeURIComponent(id)}`),
  create:(data:ResidentInput)=>request<Resident>('/residents',{method:'POST',body:JSON.stringify(data)}),
  update:(id:string,data:ResidentInput,version:number,change_reason:string)=>request<Resident>(`/residents/${encodeURIComponent(id)}`,{method:'PUT',body:JSON.stringify({...data,version,change_reason})}),
  assignees:()=>request<{id:string;name:string;phone_hint:string}[]>('/residents/assignees'),
  changes:(id:string,page=1)=>request<{items:ResidentChange[];page:number;page_size:number}>(`/residents/${encodeURIComponent(id)}/changes?page=${page}`),
}
