import type { AGENTS } from '../demo/data'
export type Agent = (typeof AGENTS)[number]
export interface KnowledgeDocument { id: string; name: string; type: string; size: string; uploadAt: string; source: string; text: string; status: string; parsing: boolean }
export interface Chunk { id: string; docId: string; index: number; text: string; chars: number; start: number; vectorized: boolean; vector: Float32Array | null }
export interface Hit { chunk: Chunk; score: number; cos: number }
export interface Message { role: 'user' | 'assistant'; text: string; time: string; welcome?: boolean; chips?: string[]; hits?: Hit[]; status?: string; streaming?: boolean; feedback?: string }
export interface SearchState { q: string; results: Hit[]; took: number; scope: string; topK: number; threshold: number; ran: boolean }
export interface RetrievalLog extends SearchState { id: string; time: string }
export interface ServiceRecord { agentId: string; q: string; time: string; hits: number; demo?: boolean; status?: string }
