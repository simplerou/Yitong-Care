import { authApi, sessionToken, clearSession } from '../api/auth'
export async function authGuard(to: {meta: {layout?: unknown; adminOnly?: unknown; staffOnly?: unknown; residentOnly?: unknown}}) {
  if (to.meta.layout === 'auth') return true
  if (!sessionToken()) return { name: 'login' }
  try {
    const account = await authApi.me()
    if(account.role === 'resident'){ clearSession(); return {name:'login'} }
    if(['medical','kitchen','nursing','finance'].includes(account.role || '') && (to as {path?:string}).path && !(to as {path?:string}).path?.startsWith('/operations'))return {name:'operations'}
    if(to.meta.adminOnly && account.role !== 'admin')return {name:'home'}
    if(to.meta.staffOnly && !['admin','user'].includes(account.role || ''))return {name:'login'}
    if(to.meta.residentOnly)return {name:'home'}
    return true
  }
  catch { clearSession(); return { name: 'login' } }
}
