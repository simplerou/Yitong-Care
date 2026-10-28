import { request } from './http'
import type { ChunkDto } from './chunks'

export interface DocumentDto {
  id: string; kb_id: string; name: string; type: string; size: number; source: string | null
  status: string; error_message: string | null; chunk_count: number; vector_count: number
  created_at: string; updated_at: string
}
export interface DocumentDetailDto extends DocumentDto { content: string | null; chunks: ChunkDto[] }
export interface KnowledgeStats { documents: number; chunks: number; vectors: number; pending: number }
export interface DocumentPage { items: DocumentDto[]; total: number; page: number; page_size: number; stats: KnowledgeStats }
export interface KnowledgeBase { id: string; name: string }

export const documentsApi = {
  list(q = '', page = 1, pageSize = 20) {
    return request<DocumentPage>(`/documents?${new URLSearchParams({ q, page: String(page), page_size: String(pageSize) })}`)
  },
  bases: () => request<KnowledgeBase[]>('/knowledge-bases'),
  detail: (id: string) => request<DocumentDetailDto>(`/documents/${encodeURIComponent(id)}`),
  upload(file: File, kbId: string, source: string) {
    const form = new FormData()
    form.append('file', file); form.append('kb_id', kbId); form.append('source', source)
    return request<DocumentDto>('/documents', { method: 'POST', body: form })
  },
  retry: (id: string) => request<DocumentDto>(`/documents/${encodeURIComponent(id)}/parse:retry`, { method: 'POST' }),
  remove: (id: string) => request<void>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
