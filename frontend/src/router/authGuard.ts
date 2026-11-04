import { authApi, sessionToken, clearSession } from '../api/auth'
export async function authGuard(to: {meta: {layout?: unknown; adminOnly?: unknown; staffOnly?: unknown; residentOnly?: unknown}}) {
  if (to.meta.layout === 'auth') return true
  if (!sessionToken()) return { name: 'login' }
  try {
    const account = await authApi.me()
    if(to.meta.adminOnly && account.role !== 'admin')return {name:account.role==='resident'?'my-profile':'home'}
    if(to.meta.staffOnly && account.role === 'resident')return {name:'my-profile'}
    if(to.meta.residentOnly && account.role !== 'resident')return {name:'home'}
    return true
  }
  catch { clearSession(); return { name: 'login' } }
}
