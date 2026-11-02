<script setup lang="ts">
import AppSelect from '../common/AppSelect.vue'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useHealthChatStore } from '../../stores/healthChat'
import { healthApi, type HealthAnswer, type HealthCitation, type HealthConfig } from '../../api/health'
import type { LocalCitation, WebSource } from '../../api/chat'
import { safeWebUrl } from '../../api/chat'
import type { Agent, Chunk, KnowledgeDocument } from '../../types/models'
import { useOverlay } from '../../composables/useOverlay'
import AppBreadcrumb from '../layout/AppBreadcrumb.vue'
import ChatComposer from './ChatComposer.vue'
import WebSourceSnapshot from './WebSourceSnapshot.vue'
import UrgencyBanner from '../health/UrgencyBanner.vue'
import VitalsCard from '../health/VitalsCard.vue'

const props = defineProps<{ agent: Agent }>()
const ui = useOverlay(), body = ref<HTMLElement>(), store = useHealthChatStore()
const { busy, error, latest } = storeToRefs(store)
const workflowLabels: Record<string, string> = {
  understand: '正在理解问题', assess_vitals: '正在解析测量数值', triage: '正在判断就医优先级',
  emergency: '正在给出急救提示', clarify: '正在整理需要补充的信息', retrieve: '正在检索健康知识库',
  web_search: '正在检索官方健康资料', web_refine: '正在补充检索', generate: '正在整理有依据的回答',
  validate: '正在检查引用与数值', verify_grounding: '正在核对答案与原文', insufficient: '正在整理资料不足说明',
  completed: '回答已完成', failed: '本次回答未完成',
}
const progressLabel = computed(() => store.loading ? '正在加载会话' : workflowLabels[store.stage || store.turns.at(-1)?.stage || 'understand'] || '正在处理问题')
const webSnapshot = ref<WebSource | null>(null)
const configuration = ref<HealthConfig | null>(null), configError = ref('')

const messages = computed(() => store.turns.flatMap(turn => [
  { role: 'user' as const, text: turn.question, turnId: turn.id, failed: false, response: undefined as HealthAnswer | undefined },
  ...(turn.response
    ? [{ role: 'assistant' as const, text: turn.response.answer, turnId: turn.id, failed: false, response: turn.response as HealthAnswer | undefined }]
    : turn.status === 'failed'
      ? [{ role: 'assistant' as const, text: turn.error || '上次任务未完成，未保存最终答案。', turnId: turn.id, failed: true, response: undefined as HealthAnswer | undefined }]
      : []),
]))
const retrieved = computed<LocalCitation[]>(() => (latest.value?.retrieved_hits || []).map((hit, index) => ({ index: index + 1, hit })))
const citationList = computed<HealthCitation[]>(() => latest.value?.citations || [])
const latestTurn = computed(() => store.turns.find(turn => turn.id === store.evidenceTurnId))

async function loadConfig() {
  try { configuration.value = await healthApi.config(); configError.value = '' }
  catch (e) { configError.value = e instanceof Error ? e.message : '配置加载失败' }
}
onMounted(() => { void loadConfig(); void store.initialize() })
onUnmounted(() => store.stop())
watch(() => messages.value.length, async () => { await nextTick(); if (body.value) body.value.scrollTop = body.value.scrollHeight })
watch(() => store.active?.id, () => { webSnapshot.value = null })

function send(question: string) { void store.send(question) }
function retry() { if (configError.value) void loadConfig(); else void store.retry() }
function clear() {
  if (!busy.value && store.active) ui.confirm('删除会话', '删除当前会话及其保存的问答、指标判读与来源快照？知识库文档和检索记录不受影响。', () => { void store.remove() }, '删除')
}
function parts(text: string) { return text.split(/(【\d+】)/g) }
function citationIndex(text: string) { return /^【\d+】$/.test(text) ? Number(text.slice(1, -1)) : 0 }
function citationOf(index: number, response?: HealthAnswer) { return response?.citations.find(item => item.index === index) }
function open(citation: HealthCitation, response: HealthAnswer, items: HealthCitation[] = response.citations) {
  if (citation.source_type === 'web') { webSnapshot.value = citation.web; return }
  const locals = items.filter((item): item is LocalCitation => item.source_type !== 'web' && !!item.hit)
  const chunk = (item: LocalCitation): Chunk => ({
    id: `server-${item.hit.chunk_id}`, docId: item.hit.doc_id, index: item.hit.seq, text: item.hit.text,
    chars: item.hit.chars, start: item.hit.start, vectorized: true, vector: null,
  })
  const doc = (item: LocalCitation): KnowledgeDocument => ({
    id: item.hit.doc_id, name: item.hit.doc_name, kbId: item.hit.kb_id, type: item.hit.type, size: '—',
    uploadAt: '—', source: item.hit.source, text: item.hit.text, status: 'vectorized', parsing: false, persisted: true,
  })
  ui.open({ kind: 'chunk', title: '健康资料原文依据', chunk: chunk(citation), doc: doc(citation), chunks: locals.map(chunk), documents: locals.map(doc), index: locals.findIndex(item => item.index === citation.index) })
}
function cite(index: number, response?: HealthAnswer) { const citation = citationOf(index, response); if (citation && response) open(citation, response) }
function answerLabel(response: HealthAnswer) {
  if (response.status === 'emergency') return '紧急处理提示'
  if (response.status === 'clarification') return '需要补充信息'
  if (response.status === 'insufficient') return '资料不足'
  if (response.answer_checks?.status === 'partial') return '部分依据通过检查'
  return '依据资料回答'
}
function checkLabel(response: HealthAnswer) {
  if (!response.answer_checks) return ''
  if (response.answer_checks.status === 'error') return '检查未完成'
  if (response.answer_checks.status === 'blocked') return '依据未通过检查'
  if (response.answer_checks.status === 'partial') return '部分段落未通过检查'
  return ''
}
</script>

<template>
  <div class="page">
    <AppBreadcrumb />
    <div class="card agent-head" :style="{ '--tint': props.agent.tint, '--c': props.agent.color }">
      <span class="agent-ico"><AppIcon :name="props.agent.icon" :size="26" /></span>
      <div class="agent-id">
        <h1>健康管家 <span class="badge green">知识库问答</span></h1>
        <p>指标解读与慢病生活方式 · 紧急情况优先给出急救提示 · 回答附原文依据</p>
      </div>
      <div class="agent-actions">
        <button class="btn sm" :disabled="busy || store.unconfirmed" @click="store.create">新建会话</button>
        <button class="btn sm" :disabled="busy || !store.active || store.unconfirmed" @click="clear">删除会话</button>
      </div>
    </div>

    <div class="agent-layout">
      <section class="card chat-panel" :aria-busy="busy">
        <div class="chat-head">
          <b>对话</b><span class="badge violet">RAG 增强</span>
          <span class="chat-head-right">{{ configuration?.model || '模型配置加载中' }}</span>
        </div>
        <div class="session-controls">
          <label for="health-session">历史会话</label>
          <AppSelect id="health-session" class="select" :value="store.active?.id || ''" :disabled="busy || store.unconfirmed" @change="store.select(String($event))">
            <option disabled value="">{{ store.sessions.length ? '请选择会话' : '尚无历史会话，发送问题后自动创建' }}</option>
            <option v-if="store.active && !store.sessions.some(s => s.id === store.active?.id)" :value="store.active.id">{{ store.active.title }}</option>
            <option v-for="session in store.sessions" :key="session.id" :value="session.id">{{ session.title }}</option>
          </AppSelect>
          <button v-if="store.sessions.length < store.total" class="btn sm" :disabled="busy" @click="store.moreSessions">更多会话</button>
        </div>
        <p class="src-meta">
          范围：{{ configuration?.knowledge_scope.join(' / ') || '尚未加载' }} · 判读表 {{ configuration?.table_version || '加载中' }} ·
          分级与就医优先级由程序规则计算，问答与当次判读已保存。
          {{ configuration?.web_configured ? '联网检索已配置，按需查询官方资料。' : '联网检索未配置，当前使用本地资料。' }}
        </p>

        <div ref="body" class="chat-body" aria-live="polite">
          <button v-if="store.hasMore" class="btn sm" :disabled="busy" @click="store.older">加载更早的问答</button>
          <div v-if="!messages.length" class="msg">
            <div class="bubble">您好，我是健康管家。可以告诉我最近的血压、血糖、血氧等测量值和测量时间，我会结合健康知识库解读这些数值，并说明什么时候需要就医。紧急情况请直接拨打 120。</div>
          </div>
          <div v-for="(message, index) in messages" :key="index" class="msg" :class="{ user: message.role === 'user' }">
            <div class="msg-main">
              <div class="msg-head">
                <b>{{ message.role === 'user' ? '我' : '健康管家' }}</b>
                <button v-if="message.failed && store.turns.at(-1)?.id === message.turnId" class="link-btn" :disabled="busy" @click="retry">重试本条</button>
                <button v-if="message.response" class="link-btn" :aria-pressed="store.evidenceTurnId === message.turnId" @click="store.evidenceTurnId = message.turnId">查看本次依据</button>
                <span v-if="message.response">{{ answerLabel(message.response) }}</span>
              </div>
              <div class="bubble">
                <UrgencyBanner
                  v-if="message.response && (message.response.urgency === 'L1' || message.response.urgency === 'L2' || message.response.status === 'emergency')"
                  :urgency="message.response.urgency" :status="message.response.status"
                  :red-flags="message.response.red_flags_observed" :required-action="message.response.required_action" />
                <VitalsCard v-if="message.response?.vitals_assessment" :assessment="message.response.vitals_assessment" />
                <div class="msg-text">
                  <p v-if="message.response?.coverage === 'partial'" class="partial-answer-label">已核对到的部分</p>
                  <p v-for="(paragraph, paragraphIndex) in message.text.split('\n').filter(Boolean)" :key="paragraphIndex">
                    <template v-for="(part, partIndex) in parts(paragraph)" :key="partIndex">
                      <button v-if="citationIndex(part) && message.response?.citations.some(c => c.index === citationIndex(part))" class="link-btn" :aria-label="`查看健康依据 ${citationIndex(part)}`" @click="cite(citationIndex(part), message.response)">{{ part }}</button>
                      <template v-else>{{ part }}</template>
                    </template>
                  </p>
                  <section v-if="message.response?.route_suggestion" class="route-hint" aria-label="转接建议">
                    <b>可以转接其他管家</b>
                    <p>{{ message.response.route_suggestion.reason }}</p>
                  </section>
                  <section v-if="message.response?.general_info?.length" class="general-concepts" aria-label="通用概念说明">
                    <b>通用概念说明 · 不代表个体结论</b>
                    <p v-for="(info, infoIndex) in message.response.general_info" :key="infoIndex">{{ info }}</p>
                  </section>
                </div>
              </div>
            </div>
          </div>
          <div v-if="busy" class="rag-status" role="status"><span class="spinner"></span>{{ progressLabel }}，请稍候…</div>
        </div>
        <div v-if="error || configError" class="document-error" role="alert">{{ error || configError }} <button class="btn sm" :disabled="busy" @click="retry">重试</button></div>
        <ChatComposer placeholder="例如：早上量的血压 150/95，头有点晕，需要去医院吗？" :busy="busy || store.unconfirmed || !configuration?.configured" @send="send" />
        <p v-if="configuration && !configuration.configured" class="document-error">请在后端配置聊天模型后再提问。</p>
        <p v-if="configuration && !configuration.enabled" class="document-error">健康管家当前未启用，请在后端设置 HEALTH_ENABLED=true。</p>
      </section>

      <aside class="card src-panel health-sources">
        <div class="src-head">
          <b>本次依据</b>
          <span class="badge blue">{{ retrieved.length }} 条本地片段 · {{ latest?.web_sources?.length || 0 }} 条网页 · {{ latest?.citations.length || 0 }} 条引用</span>
        </div>
        <p v-if="latestTurn" class="src-meta">{{ latestTurn.question }} · 保存于 {{ new Date(latestTurn.updated_at).toLocaleString('zh-CN') }} · 来源模型 {{ latest?.model }}，回放不重新核验。</p>
        <p class="src-meta" role="status">
          {{ !latest ? '提问后展示本次判读与召回资料。' : !latest.retrieval_log_id ? '本次未执行检索，请查看左侧追问或急救提示。' : `已执行检索，范围内可用向量 ${latest.vector_count} 条，召回 ${retrieved.length} 条片段。召回不等于已被答案引用。` }}
        </p>
        <UrgencyBanner v-if="latest && (latest.urgency === 'L1' || latest.urgency === 'L2')" :urgency="latest.urgency" :status="latest.status" :red-flags="latest.red_flags_observed" :required-action="latest.required_action" />
        <VitalsCard v-if="latest?.vitals_assessment" :assessment="latest.vitals_assessment" />
        <p v-if="latest?.answer_checks" class="src-meta">
          原文一致性检查：{{ checkLabel(latest) || '通过' }} · 检查 {{ latest.answer_checks.checked_paragraphs }} 段，保留 {{ latest.answer_checks.accepted_paragraphs }} 段
        </p>
        <details v-if="latest?.metrics" class="src-meta">
          <summary>本次处理耗时 {{ (latest.metrics.total_ms / 1000).toFixed(1) }} 秒 · 模型调用 {{ latest.metrics.llm_calls }} 次</summary>
          <p v-for="(ms, stageName) in latest.metrics.stage_ms" :key="stageName">{{ workflowLabels[String(stageName)] || stageName }}：{{ (ms / 1000).toFixed(2) }} 秒</p>
          <p>模型异常 {{ latest.metrics.llm_failures }} 次；历史回放展示的是原执行统计。</p>
        </details>
        <details v-if="latest?.web_diagnostics" class="src-meta">
          <summary>联网过程：搜索 {{ latest.web_diagnostics.search_count }} 条 → 正文 {{ latest.web_diagnostics.body_count }} 条 → 保留 {{ latest.web_diagnostics.accepted_count }} 条</summary>
          <p v-if="latest.web_diagnostics.search_query">实际搜索：{{ latest.web_diagnostics.search_query }}</p>
          <p v-for="(count, reason) in latest.web_diagnostics.rejected_counts" :key="reason">未采用（{{ reason }}）：{{ count }} 条</p>
        </details>
        <div class="src-list">
          <div v-if="!retrieved.length" class="src-empty">{{ latest?.retrieval_log_id ? '本次没有召回片段，可核对知识库范围或入库状态。' : '尚无检索结果。' }}</div>
          <button v-for="citation in retrieved" :key="citation.index" class="src-item" @click="open(citation, latest!, citationList.length ? citationList : retrieved)">
            <div class="src-item-top">
              <span class="src-idx">{{ citation.index }}</span>
              <span class="src-title">{{ citation.hit.doc_name }}</span>
              <span class="src-score">RRF {{ citation.hit.score.toFixed(6) }}</span>
            </div>
            <p class="src-snip">{{ citation.hit.text.slice(0, 100) }}…</p>
            <div class="src-foot2"><span>{{ citation.hit.source }}</span><span>第 {{ citation.hit.seq }} 段</span><span>{{ latest?.citations.some(c => c.index === citation.index) ? '答案已引用' : '仅检索命中' }}</span></div>
          </button>
          <article v-for="(source, index) in latest?.web_sources || []" :key="source.url" class="src-item web-source">
            <button type="button" class="web-snapshot-open" :aria-label="`查看保存的网页正文：${source.title}`" @click="webSnapshot = source">
              <div class="src-item-top"><span class="src-idx">{{ retrieved.length + index + 1 }}</span><span class="src-title">{{ source.title }}</span><span class="badge blue">网络正文</span></div>
              <p class="src-snip">{{ source.content.slice(0, 140) }}…</p>
              <div class="src-foot2"><span>{{ source.published_date ? '发布日期：' + source.published_date : '发布日期待核实' }}</span><span>获取于 {{ new Date(source.retrieved_at).toLocaleString('zh-CN') }}</span></div>
            </button>
            <a class="web-source-link" :href="safeWebUrl(source.url) || undefined" target="_blank" rel="noopener noreferrer"><span class="web-source-url">{{ source.url }}</span><span>查看官网 ↗</span></a>
          </article>
        </div>
        <p class="src-meta">健康管家提供科普信息，不构成诊断或处方；分级表与规则命中记录可复核，个体用药与目标请遵医嘱。</p>
      </aside>
    </div>
    <WebSourceSnapshot v-if="webSnapshot" :source="webSnapshot" @close="webSnapshot = null" />
  </div>
</template>

<style scoped>
.partial-answer-label { font-weight: 600; color: var(--brand); }
.general-concepts, .route-hint { margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--line); color: var(--ink-2); }
.general-concepts b, .route-hint b { font-size: 13px; }
.session-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 10px 16px; border-bottom: 1px solid var(--line); }
.session-controls label { color: var(--muted); font-size: 12px; }
.session-controls .select { min-width: 0; flex: 1 1 200px; max-width: 100%; }
.health-sources { min-width: 0; }
.health-sources > .src-head { flex: 0 0 auto; flex-wrap: wrap; }
.health-sources > .src-head .badge { max-width: 100%; white-space: normal; }
.health-sources > .src-meta { flex: 0 0 auto; margin: 0; overflow-wrap: anywhere; }
.health-sources > details.src-meta { max-height: 180px; overflow-y: auto; }
.health-sources summary { cursor: pointer; line-height: 1.7; }
.health-sources .src-list { min-height: 0; min-width: 0; overscroll-behavior: contain; }
.health-sources .src-item { display: block; width: 100%; min-width: 0; box-sizing: border-box; text-align: left; }
.health-sources .src-title { min-width: 0; overflow-wrap: anywhere; }
.health-sources .src-foot2 { flex-wrap: wrap; justify-content: flex-start; gap: 4px 12px; line-height: 1.6; overflow-wrap: anywhere; }
.web-snapshot-open { display: block; width: 100%; min-width: 0; border: 0; padding: 0; text-align: left; color: inherit; background: transparent; font: inherit; cursor: pointer; }
.web-source { color: inherit; text-decoration: none; }
.web-source .src-snip { overflow-wrap: anywhere; }
.web-source-link { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 10px; padding-top: 8px; margin-top: 8px; border-top: 1px solid var(--line); font-size: 11px; line-height: 1.6; color: var(--brand); text-decoration: none; }
.web-source-url { min-width: 0; flex: 1 1 180px; color: var(--muted); overflow-wrap: anywhere; }
</style>
