import { authApi, sessionToken, clearSession } from '../api/auth'
export async function authGuard(to: {meta: {layout?: unknown; adminOnly?: unknown}}) {
  if (to.meta.layout === 'auth') return true
  if (!sessionToken()) return { name: 'login' }
  try { const account = await authApi.me(); return to.meta.adminOnly && account.role !== 'admin' ? { name: 'home' } : true }
  catch { clearSession(); return { name: 'login' } }
}
