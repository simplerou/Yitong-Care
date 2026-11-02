import { request } from './http'
export interface RecentConversation { id: string; agentId: string; title: string; updated_at: string }
const scopes = [ ['policy','policy'], ['health','health'], ['medication','med'], ['diet','diet'], ['safety','safety'], ['mind','mind'] ] as const
export async function loadRecentConversations() {
  const results = await Promise.allSettled(scopes.map(async ([backend, agentId]) => {
    const page = await request<{items:{id:string;title:string;updated_at:string}[]}>(`/agents/${backend}/conversations?page=1&page_size=4`)
    return page.items.map(row => ({...row, agentId}))
  }))
  return {
    items: results.flatMap(result => result.status === 'fulfilled' ? result.value : []).sort((a,b) => Date.parse(b.updated_at)-Date.parse(a.updated_at)).slice(0,4),
    failed: results.filter(result => result.status === 'rejected').length,
  }
}
