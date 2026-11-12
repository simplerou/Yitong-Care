import { authApi, sessionToken, clearSession } from '../api/auth'
export async function authGuard(to: {meta: {layout?: unknown; adminOnly?: unknown; staffOnly?: unknown; residentOnly?: unknown; roles?:unknown}}) {
  if (to.meta.layout === 'auth') return true
  if (!sessionToken()) return { name: 'login' }
  try {
    const account = await authApi.me()
    if(account.status==='disabled'){clearSession();return {name:'login'}}
    if(account.status&&account.status!=='active')return to.meta.layout==='account'?true:{name:'application-status'}
    if(to.meta.layout==='account')return {name:'operations'}
    if(account.role === 'resident'){ clearSession(); return {name:'login'} }
    if(Array.isArray(to.meta.roles)&&!to.meta.roles.includes(account.role))return {name:'operations'}
    if(to.meta.adminOnly && account.role !== 'admin')return {name:'home'}
    if(to.meta.staffOnly && !['admin','user'].includes(account.role || ''))return {name:'login'}
    if(to.meta.residentOnly)return {name:'home'}
    return true
  }
  catch { clearSession(); return { name: 'login' } }
}
