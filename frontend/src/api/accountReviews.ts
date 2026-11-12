import {request} from './http'
import type {Account} from './auth'
export interface Application extends Account {phone_hint:string;application_version:number}
export const roleNames:Record<string,string>={resident:'历史老人账号',admin:'院长',user:'护工',medical:'医务室',kitchen:'食堂',nursing:'护理部',finance:'财务部'}
export const reviews={
 list:(status='pending',page=1)=>request<{items:Application[];total:number;page:number;page_size:number}>(`/account-reviews?${new URLSearchParams({status,page:String(page)})}`),
 decide:(id:string,data:unknown)=>request<Account>(`/account-reviews/${encodeURIComponent(id)}/decision`,{method:'POST',body:JSON.stringify(data)}),
 status:(id:string,data:unknown)=>request<Account>(`/account-reviews/${encodeURIComponent(id)}/status`,{method:'PUT',body:JSON.stringify(data)}),
 reapply:(data:unknown)=>request<Account>('/auth/application',{method:'PUT',body:JSON.stringify(data)}),
}
