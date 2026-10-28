import { computed, reactive, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { AGENTS, DOC_SEED, DEMO_DOC, RECENT } from '../demo/data'
import { chunkText, embed, cosine, bigrams, splitSents } from '../demo/rag.js'
import type { Agent, KnowledgeDocument, Chunk, Hit, Message, SearchState, RetrievalLog, ServiceRecord } from '../types/models'
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
const uid = (prefix: string) => `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
const time = () => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
const fullTime = () => `${new Date().getMonth() + 1}-${new Date().getDate()} ${time()}`
export const useDemoStore = defineStore('demo', () => {
  let preference = false
  try { preference = localStorage.getItem('yyt.senior') === '1' } catch { /* 隐私模式 */ }
  const senior = ref(preference)
  const toast = ref<{ text: string; type: string } | null>(null)
  let toastTimer: ReturnType<typeof setTimeout>
  function notify(text: string, type = 'success') {
    clearTimeout(toastTimer)
    toast.value = { text, type }
    toastTimer = setTimeout(() => { toast.value = null }, 2800)
  }
  watch(senior, value => {
    document.documentElement.classList.toggle('senior', value)
    try { localStorage.setItem('yyt.senior', value ? '1' : '0') } catch { /* 隐私模式 */ }
  }, { immediate: true })
  function toggleSenior() { senior.value = !senior.value; notify(senior.value ? '已开启长辈模式：字号与按钮更大' : '已恢复标准模式') }
  const state = reactive({
    docs: [] as KnowledgeDocument[], chunks: [] as Chunk[], history: [] as RetrievalLog[],
    chats: {} as Record<string, Message[]>, lastHits: {} as Record<string, Hit[]>, lastQuery: {} as Record<string, string>,
    search: { q: '', results: [], took: 0, scope: 'all', topK: 5, threshold: 0.12, ran: false } as SearchState,
    chunkCfg: { docId: 'd3', size: 220, overlap: 30 },
    vecCfg: { docId: 'd1', model: 'bge-large-zh-v1.5', batch: 16 },
    busy: false, vectorBusy: false, vectorProgress: 0, vectorStep: -1, vectorSub: '', vecLog: [] as string[],
    reminders: [
      { id: 'r1', title: '晨起降压药 · 苯磺酸氨氯地平 5mg', sub: '每日 1 次 · 早餐后', time: '08:00', done: true },
      { id: 'r2', title: '测量并记录晨起血压', sub: '目标 < 150/90 mmHg', time: '08:10', done: false },
      { id: 'r3', title: '午间助餐 · 社区老年食堂', sub: '低盐窗口 · 已预订', time: '11:30', done: false },
      { id: 'r4', title: '傍晚散步 30 分钟', sub: '家属陪同 · 穿防滑鞋', time: '17:30', done: false }
    ]
  })
  const vectorCount = computed(() => state.chunks.filter(c => c.vectorized).length)
  const pendingCount = computed(() => state.reminders.filter(r => !r.done).length)
  const services = computed<ServiceRecord[]>(() => {
    const rows: ServiceRecord[] = []
    Object.entries(state.chats).forEach(([agentId, messages]) => messages.forEach((m, i) => {
      if (m.role === 'user') rows.unshift({ agentId, q: m.text, time: m.time, hits: messages[i+1]?.hits?.length || 0, status: messages[i+1]?.status === 'done' ? '已回复' : '处理中' })
    }))
    return [...rows, ...RECENT.map(r => ({ ...r, demo: true }))]
  })
  function buildChunks(doc: KnowledgeDocument): Chunk[] {
    let cursor = 0
    return chunkText(doc.text, state.chunkCfg.size, state.chunkCfg.overlap).map((text: string, i: number) => {
      const found = doc.text.indexOf(text, Math.max(0, cursor - state.chunkCfg.overlap - 8))
      const start = found < 0 ? cursor : found
      cursor = start + text.length
      return { id: `${doc.id}-c${i+1}`, docId: doc.id, index: i+1, text, chars: text.length, start, vectorized: false, vector: null }
    })
  }
  DOC_SEED.forEach(raw => {
    const doc: KnowledgeDocument = { ...raw, status: 'vectorized', parsing: false }
    state.docs.push(doc)
    const chunks = buildChunks(doc)
    chunks.forEach(c => { c.vector = embed(c.text); c.vectorized = true })
    state.chunks.push(...chunks)
  })
  function retrieve(docIds: string[] | "all", query: string, topK = 5, threshold = 0.12): Hit[] {
    if (!query.trim()) return [];
    const qv = embed(query);
    const pool = state.chunks.filter(
      (c) => c.vectorized && (docIds === "all" || docIds.includes(c.docId))
    );
    if (!pool.length) return [];
    const grams = bigrams(query);
    const df = new Map<string, number>(grams.map((g) => [g, 0]));
    pool.forEach((c) => grams.forEach((g) => {
      if (c.text.includes(g)) df.set(g, (df.get(g) || 0) + 1);
    }));
    const weight = (g: string) => Math.log(1 + pool.length / (1 + (df.get(g) || 0)));
    // 只统计在知识库中出现过的查询词，避免数字、虚词拉低覆盖率
    const valid = grams.filter((g) => (df.get(g) || 0) > 0);
    const weightSum = valid.reduce((n, g) => n + weight(g), 0) || 1;
    const rare = [...valid].sort((a, b) => weight(b) - weight(a)).slice(0, 3);
    const docMap = new Map(state.docs.map((d) => [d.id, d]));
    const normQuery = query.replace(/[\s，。！？；：、,.!?;:"'（）()【】]/g, "");
    return pool
      .map((c) => {
        const cos = cosine(qv, c.vector!);
        let lex = 0;
        valid.forEach((g) => { if (c.text.includes(g)) lex += weight(g); });
        lex = lex / weightSum;
        const bonus = normQuery.length >= 2 && c.text.includes(normQuery) ? 0.12 : 0;
        const doc = docMap.get(c.docId);
        const titleBoost = doc && rare.some((g) => doc.name.includes(g)) ? 0.16 : 0;
        const score = Math.min(0.98, 0.52 * cos + 0.48 * lex + bonus + titleBoost);
        return { chunk: c, score, cos };
      })
      .filter((r) => r.score >= threshold)
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);
  }

  function composeAnswer(a: Agent, q: string, hits: Hit[]) {
    if (!hits.length) {
      return `抱歉，我在「${a.name}」可访问的知识库中没有检索到与这个问题直接相关的内容。\n您可以换一种说法，或者点击右上角「转人工」，由社区养老顾问为您跟进。`;
    }
    const qgrams = bigrams(q);
    const safety = /(加药|减药|停药|换药|调整用药|用药|吃药|漏服|补服)/.test(q) &&
      (a.id === "health" || a.id === "med")
      ? "\n先提醒一句：用药方案是否调整需要医生结合近期指标判断，请勿自行加量、减量或停药。"
      : "";
    const lines = hits.map((h, i) => {
      const sents: string[] = splitSents(h.chunk.text).filter((s: string) => s.length > 8);
      const scored = sents.map((s, idx) => ({
        s, idx, sc: qgrams.reduce((n, g) => n + (s.includes(g) ? 1 : 0), 0)
      })).sort((x, y) => y.sc - x.sc).slice(0, 2).sort((x, y) => x.idx - y.idx);
      let text = (scored.length ? scored : sents.slice(0, 2).map((s, idx) => ({ s, idx })))
        .map((x) => x.s).join("");
      text = text.replace(/\s+/g, "");
      if (!text) text = h.chunk.text.slice(0, 90);
      if (text.length > 112) text = text.slice(0, 112).replace(/[，、；]$/, "") + "…";
      return `${i + 1}. ${text} 【${i + 1}】`;
    }).join("\n");
    return `${a.lead}${safety}\n${lines}\n${a.closing}`;
  }


  function search(q = state.search.q, record = true) {
    if (!q.trim()) { notify('请先输入检索内容', 'warn'); return }
    const started = performance.now()
    const results = retrieve(state.search.scope === 'all' ? 'all' : [state.search.scope], q.trim(), state.search.topK, state.search.threshold)
    state.search = { ...state.search, q: q.trim(), results, took: Math.max(9, Math.round(performance.now() - started)), ran: true }
    if (record) state.history.unshift({ ...state.search, results: results.map(r => ({ ...r, chunk: { ...r.chunk, vector: null } })), id: uid('h'), time: fullTime() })
    notify(results.length ? `检索完成，命中 ${results.length} 条片段` : '未命中达到阈值的内容', results.length ? 'success' : 'warn')
  }
  function ensureChat(a: Agent) {
    if (!state.chats[a.id]) state.chats[a.id] = [{ role: 'assistant', text: a.welcome, time: `今天 ${time()}`, welcome: true, chips: a.chips, hits: [], status: 'done' }]
    if (!state.lastHits[a.id]) state.lastHits[a.id] = []
  }
  async function ask(a: Agent, text: string, regenerate = false) {
    if (state.busy) return
    const q = text.trim()
    if (!q) { notify('请先输入问题', 'warn'); return }
    ensureChat(a)
    const chat = state.chats[a.id]
    if (regenerate) { while (chat.at(-1)?.role === 'assistant' && !chat.at(-1)?.welcome) chat.pop() }
    else chat.push({ role: 'user', text: q, time: `今天 ${time()}` })
    chat.push({ role: 'assistant', text: '', time: `今天 ${time()}`, status: 'retrieving', hits: [], streaming: true })
    const msg = chat[chat.length-1]
    state.lastQuery[a.id] = q
    state.busy = true
    try {
      await sleep(700)
      let hits = retrieve(a.kbIds, q, 3, .1)
      if (!hits.length) hits = retrieve(a.kbIds, q, 3, .02)
      msg.hits = hits; state.lastHits[a.id] = hits; msg.status = 'generating'
      await sleep(320)
      const answer = composeAnswer(a, q, hits)
      for (let i = 7; i < answer.length + 7; i += 7) { msg.text = answer.slice(0, i); await sleep(24) }
      msg.status = 'done'
      if (hits.length) notify(`回答已生成，引用 ${hits.length} 条知识库原文`)
    } finally { msg.streaming = false; state.busy = false }
  }
  function clearChat(a: Agent) { delete state.chats[a.id]; state.lastHits[a.id] = []; state.lastQuery[a.id] = ''; ensureChat(a); notify('对话已清空') }
  function commitChunks(doc: KnowledgeDocument) {
    if (state.vectorBusy || state.busy) { notify('请等待当前任务完成后再切块', 'warn'); return }
    const chunks = buildChunks(doc)
    if (!chunks.length) { notify('没有可切块的正文', 'error'); return }
    state.chunks = state.chunks.filter(c => c.docId !== doc.id).concat(chunks)
    doc.status = 'chunked'
    state.search.results = state.search.results.filter(r => r.chunk.docId !== doc.id)
    notify(`已保存 ${chunks.length} 个文本块，请重新执行向量入库`)
  }
  async function vectorize() {
    if (state.vectorBusy) return
    const doc = state.docs.find(d => d.id === state.vecCfg.docId)
    if (!doc) return
    const chunks = state.chunks.filter(c => c.docId === doc.id)
    if (!chunks.length) { notify('请先完成文本切块', 'warn'); return }
    state.vectorBusy = true; state.vectorProgress = 0; state.vectorStep = 0; state.vecLog = []
    const log = (text: string) => state.vecLog.push(`[${time()}] ${text}`)
    try {
      log(`开始处理「${doc.name}」，共 ${chunks.length} 个文本块，批次大小 ${state.vecCfg.batch}`)
      await sleep(420); state.vectorStep = 1
      log(`加载模型 ${state.vecCfg.model}（演示哈希向量 · 384 维）…完成`)
      for (let i = 0; i < chunks.length; i += state.vecCfg.batch) {
        await sleep(360)
        const batch = chunks.slice(i, i + state.vecCfg.batch)
        batch.forEach(c => { c.vector = embed(c.text); c.vectorized = true })
        state.vectorProgress = Math.round(Math.min(i + batch.length, chunks.length) / chunks.length * 92)
        state.vectorSub = `正在写入第 ${Math.floor(i / state.vecCfg.batch)+1} 批 · ${Math.min(i + batch.length, chunks.length)}/${chunks.length} 段`
        log(`批次 ${Math.floor(i / state.vecCfg.batch)+1}：写入 ${batch.length} 条向量 OK`)
      }
      state.vectorStep = 2; await sleep(420)
      doc.status = 'vectorized'; state.vectorProgress = 100; state.vectorStep = 3
      state.vectorSub = `已完成 ${chunks.length} 个文本块的向量入库`
      log(`索引构建完成，集合 yyt_knowledge 新增 ${chunks.length} 条向量`)
      notify(`向量入库完成，共 ${chunks.length} 条`)
    } finally { state.vectorBusy = false }
  }
  async function addDocument(name: string, type: string, size: string, text: string, source = '本地上传') {
    const id = uid('doc')
    state.docs.unshift({ id, name, type, size, text, source, uploadAt: fullTime(), status: 'parsed', parsing: true })
    await sleep(1100)
    const doc = state.docs.find(d => d.id === id)
    if (doc) { doc.parsing = false; notify(`「${name}」解析完成，可开始切块`) }
  }
  function loadDemo() {
    if (state.docs.some(d => d.name === DEMO_DOC.name)) { notify('示例文档已在知识库中', 'warn'); return }
    void addDocument(DEMO_DOC.name, 'PDF', DEMO_DOC.size, DEMO_DOC.text, DEMO_DOC.source)
    notify('正在解析示例文档…')
  }
  async function upload(file: File) {
    const ext = file.name.split('.').pop()?.toUpperCase() || ''
    if (!['PDF', 'DOC', 'DOCX', 'TXT', 'MD', 'MARKDOWN'].includes(ext)) { notify('请选择 PDF / Word / TXT / Markdown 文件', 'error'); return }
    if (file.size > 50 * 1024 * 1024) { notify('单个文件不能超过 50MB', 'error'); return }
    const isText = ['TXT', 'MD', 'MARKDOWN'].includes(ext)
    try {
      const text = isText ? await file.text() : DEMO_DOC.text
      void addDocument(file.name, ext, file.size > 1024*1024 ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : `${Math.round(file.size / 1024)} KB`, text)
      if (!isText) notify('演示环境：PDF / Word 使用内置样例正文完成解析', 'warn')
    } catch { notify('文件读取失败，请重试', 'error') }
  }
  function removeDocument(id: string) {
    if (state.busy || state.vectorBusy) { notify('请等待当前任务完成后再删除文档', 'warn'); return }
    state.docs = state.docs.filter(d => d.id !== id); state.chunks = state.chunks.filter(c => c.docId !== id)
    state.search.results = state.search.results.filter(r => r.chunk.docId !== id)
    if (state.search.scope === id) state.search.scope = 'all'
    Object.keys(state.lastHits).forEach(aid => { state.lastHits[aid] = state.lastHits[aid].filter(h => h.chunk.docId !== id) })
    notify('文档已删除')
  }
  return { state, senior, toast, notify, toggleSenior, vectorCount, pendingCount, services, retrieve, search, ensureChat, ask, clearChat, commitChunks, vectorize, loadDemo, upload, removeDocument }
})
