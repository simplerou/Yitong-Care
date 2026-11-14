import {request} from './http'
import type {Account} from './auth'
export interface Application extends Account {phone_hint:string;application_version:number}
export const roleNames:Record<string,string>={resident:'历史老人账号',admin:'院长',user:'护工',medical:'医务室',kitchen:'食堂',nursing:'护理部',finance:'财务部'}
export interface ReviewRecord {id:string;account_id:string;applicant_name:string;phone_hint:string;reviewer_name:string;result:'approve'|'reject';requested_role:string|null;granted_role:string|null;note:string;qualification:string;valid_until:string|null;application_note:string|null;application_version:number|null;reviewed_at:string}
export const reviews={
 history:(result='all',page=1)=>request<{items:ReviewRecord[];total:number;page:number;page_size:number}>(`/account-reviews/history?${new URLSearchParams({result,page:String(page)})}`),
 list:(status='pending',page=1)=>request<{items:Application[];total:number;page:number;page_size:number}>(`/account-reviews?${new URLSearchParams({status,page:String(page)})}`),
 decide:(id:string,data:unknown)=>request<Account>(`/account-reviews/${encodeURIComponent(id)}/decision`,{method:'POST',body:JSON.stringify(data)}),
 status:(id:string,data:unknown)=>request<Account>(`/account-reviews/${encodeURIComponent(id)}/status`,{method:'PUT',body:JSON.stringify(data)}),
 reapply:(data:unknown)=>request<Account>('/auth/application',{method:'PUT',body:JSON.stringify(data)}),
}
