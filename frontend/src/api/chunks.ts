import { request } from './http'

export interface ChunkDto {
  id: number | null; doc_id: string; seq: number; content: string; start_offset: number
  chars: number; vector_status: string; overlap_chars: number
}
export interface ChunkParameters { size: number; overlap: number }
export interface ChunkResult { doc_id: string; count: number; average_chars: number; chunks: ChunkDto[] }
export const chunksApi = {
  preview: (id: string, parameters: ChunkParameters, signal?: AbortSignal) => request<ChunkResult>(
    `/documents/${encodeURIComponent(id)}/chunks:preview`, { method: 'POST', body: JSON.stringify(parameters), signal },
  ),
  save: (id: string, parameters: ChunkParameters) => request<ChunkResult>(
    `/documents/${encodeURIComponent(id)}/chunks`, { method: 'POST', body: JSON.stringify(parameters) },
  ),
}
