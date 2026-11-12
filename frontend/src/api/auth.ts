import { computed, ref } from 'vue'
import { request } from './http'
export interface Account {status?:'active'|'pending'|'rejected'|'disabled';requested_role?:string|null;application_note?:string;review_note?:string;application_version?:number;reviewed_at?:string|null; id: string; name: string; role?: 'admin' | 'user' | 'resident' | 'medical' | 'kitchen' | 'nursing' | 'finance' }
export const currentAccount = ref<Account | null>(null)
export const isAdmin = computed(() => currentAccount.value?.role === 'admin')
export const isCaregiver = computed(() => currentAccount.value?.role === 'user')
export const isNursing = computed(() => currentAccount.value?.role === 'nursing')
export const isResident = computed(() => currentAccount.value?.role === 'resident')
const key = 'yitong-session'
export function sessionToken() { return sessionStorage.getItem(key) || '' }
export function clearSession() { sessionStorage.removeItem(key); currentAccount.value = null }
export const authApi = {
  async me() { const account = await request<Account>('/auth/me'); currentAccount.value = account; return account },
  register: (data: {name: string; phone: string; password: string;requested_role?:string;application_note?:string}) => request<Account>('/auth/register', {method:'POST', body:JSON.stringify(data)}),
  async login(phone: string, password: string) {
    const result = await request<{token:string; user:Account}>('/auth/login', {method:'POST', body:JSON.stringify({phone,password})})
    sessionStorage.setItem(key, result.token)
    currentAccount.value = result.user
    return result.user
  },
  async logout() { try { await request('/auth/logout', {method:'POST'}) } finally { clearSession() } },
}
