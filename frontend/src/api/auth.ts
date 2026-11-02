import { computed, ref } from 'vue'
import { request } from './http'
export interface Account { id: string; name: string; role?: 'admin' | 'user' }
export const currentAccount = ref<Account | null>(null)
export const isAdmin = computed(() => currentAccount.value?.role === 'admin')
const key = 'yitong-session'
export function sessionToken() { return sessionStorage.getItem(key) || '' }
export function clearSession() { sessionStorage.removeItem(key); currentAccount.value = null }
export const authApi = {
  async me() { const account = await request<Account>('/auth/me'); currentAccount.value = account; return account },
  register: (data: {name: string; phone: string; password: string}) => request<Account>('/auth/register', {method:'POST', body:JSON.stringify(data)}),
  async login(phone: string, password: string) {
    const result = await request<{token:string; user:Account}>('/auth/login', {method:'POST', body:JSON.stringify({phone,password})})
    sessionStorage.setItem(key, result.token)
    currentAccount.value = result.user
    return result.user
  },
  async logout() { try { await request('/auth/logout', {method:'POST'}) } finally { clearSession() } },
}
