import { shallowRef } from 'vue'
import type { Chunk, KnowledgeDocument } from '../types/models'
export interface Overlay { kind: 'chunk' | 'preview' | 'document' | 'confirm' | 'human' | 'help' | 'notice'; title: string; subtitle?: string; chunk?: Chunk; chunks?: Chunk[]; query?: string; doc?: KnowledgeDocument; index?: number; desc?: string; okText?: string; onOk?: () => void }
const overlay = shallowRef<Overlay | null>(null)
export function useOverlay() {
  function open(value: Overlay) { overlay.value = value }
  function close() { overlay.value = null }
  function confirm(title: string, desc: string, onOk: () => void, okText = '确认') { open({ kind: 'confirm', title, desc, onOk, okText }) }
  return { overlay, open, close, confirm }
}
