import { ref } from 'vue'
import { defineStore } from 'pinia'
import { documentsApi, type DocumentDto, type KnowledgeBase, type KnowledgeStats } from '../api/documents'
import type { ChunkDto } from '../api/chunks'
import type { Chunk, KnowledgeDocument } from '../types/models'
import { useDemoStore } from './demo'
import { useOverlay } from '../composables/useOverlay'

export function mapDocument(d: DocumentDto, text = ''): KnowledgeDocument {
  return {
    id: d.id, kbId: d.kb_id, name: d.name, type: d.type,
    size: d.size >= 1024 * 1024 ? `${(d.size / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(d.size / 1024))} KB`,
    uploadAt: new Date(d.created_at).toLocaleString('zh-CN', { hour12: false }),
    source: d.source || '本地上传', text, status: d.status, parsing: d.status === 'parsing',
    chunkCount: d.chunk_count, vectorCount: d.vector_count, errorMessage: d.error_message, updatedAt: d.updated_at, persisted: true,
  }
}

export function mapChunk(c: ChunkDto): Chunk {
  return { id: c.id === null ? `preview-${c.doc_id}-${c.seq}` : `server-${c.id}`, docId: c.doc_id, index: c.seq,
    text: c.content, chars: c.chars, start: c.start_offset, vectorized: c.vector_status === 'ready',
    vector: null, overlapChars: c.overlap_chars }
}

export const useKnowledgeStore = defineStore('knowledge', () => {
  const documents = ref<KnowledgeDocument[]>([]), bases = ref<KnowledgeBase[]>([])
  const stats = ref<KnowledgeStats>({ documents: 0, chunks: 0, vectors: 0, pending: 0 })
  const total = ref(0), page = ref(1), pageSize = 20, query = ref('')
  const loading = ref(false), uploading = ref(false), error = ref(''), busyId = ref(''), detailBusy = ref(false)
  const selectedDocId = ref(''), choices = ref<KnowledgeDocument[]>([])
  const toast = useDemoStore(), ui = useOverlay()
  let version = 0

  async function load() {
    const current = ++version
    loading.value = true
    try {
      const result = await documentsApi.list(query.value, page.value, pageSize)
      if (current !== version) return
      documents.value = result.items.map(d => mapDocument(d))
      total.value = result.total; stats.value = result.stats; error.value = ''
    } catch (e) {
      if (current === version) error.value = e instanceof Error ? e.message : '文档列表加载失败。'
    } finally { if (current === version) loading.value = false }
  }

  async function loadBases() {
    try { bases.value = await documentsApi.bases() }
    catch (e) { error.value = e instanceof Error ? e.message : '知识库加载失败。' }
  }

  async function loadChoices() {
    const all: KnowledgeDocument[] = []
    let p = 1
    while (true) {
      const result = await documentsApi.list('', p, 100)
      all.push(...result.items.map(d => mapDocument(d)))
      if (all.length >= result.total || !result.items.length) break
      p++
    }
    choices.value = all
  }

  async function upload(file: File, kbId = 'general', source = '本地上传') {
    if (uploading.value) return
    if (!/\.(pdf|docx|txt|md|markdown)$/i.test(file.name)) { toast.notify('仅支持 PDF / DOCX / TXT / Markdown，旧版 DOC 请另存为 DOCX。', 'error'); return }
    if (file.size > 50 * 1024 * 1024) { toast.notify('单个文件不能超过 50MB。', 'error'); return }
    if (!file.size) { toast.notify('不能上传空文件。', 'error'); return }
    uploading.value = true
    try {
      await documentsApi.upload(file, kbId, source)
      page.value = 1; query.value = ''; await load()
      toast.notify('上传成功，正在解析正文。')
    } catch (e) { toast.notify(e instanceof Error ? e.message : '上传失败。', 'error') }
    finally { uploading.value = false }
  }

  async function detail(id: string) {
    if (detailBusy.value) return
    detailBusy.value = true
    try {
      const result = await documentsApi.detail(id)
      ui.open({ kind: 'document', title: '文档详情', subtitle: result.name, doc: mapDocument(result, result.content || ''), chunks: result.chunks.map(mapChunk) })
    } catch (e) { toast.notify(e instanceof Error ? e.message : '文档详情加载失败。', 'error') }
    finally { detailBusy.value = false }
  }

  async function remove(id: string) {
    if (busyId.value) return
    busyId.value = id
    try {
      await documentsApi.remove(id)
      if (documents.value.length === 1 && page.value > 1) page.value--
      await load(); choices.value = choices.value.filter(d => d.id !== id)
      if (selectedDocId.value === id) selectedDocId.value = ''
      toast.notify('文档及其文本块已删除。')
    } catch (e) { toast.notify(e instanceof Error ? e.message : '删除失败。', 'error') }
    finally { busyId.value = '' }
  }

  async function retry(id: string) {
    if (busyId.value) return
    busyId.value = id
    try { await documentsApi.retry(id); await load(); toast.notify('已重新开始解析。') }
    catch (e) { toast.notify(e instanceof Error ? e.message : '重试失败。', 'error') }
    finally { busyId.value = '' }
  }

  function loadDemo(kbId = 'general', source = '功能验证示例') {
    const text = '这是颐养通知识库功能验证文档，不作为医疗建议或政策办理依据。\n社区居民可以向服务窗口咨询活动安排、助餐服务和便民事项。\n工作人员可上传授权文档，核对正文，保存切块，然后进入后续的向量入库流程。\n文档保存后，刷新页面仍可查看；文本块应保留准确的原文位置。'
    return upload(new File([text], '颐养通功能验证示例.txt', { type: 'text/plain' }), kbId, source)
  }

  return { documents, bases, stats, total, page, pageSize, query, loading, uploading, error, busyId, detailBusy,
    selectedDocId, choices, load, loadBases, loadChoices, upload, detail, remove, retry, loadDemo }
})
