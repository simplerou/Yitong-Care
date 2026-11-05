<script setup lang="ts">
import AppSelect from '../common/AppSelect.vue'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useMindChatStore } from '../../stores/mindChat'
import { mindApi, type MindAnswer, type MindCitation, type MindConfig } from '../../api/mind'
import { safeWebUrl, type LocalCitation, type WebSource } from '../../api/chat'
import type { Agent, Chunk, KnowledgeDocument } from '../../types/models'
import { useOverlay } from '../../composables/useOverlay'
import AppBreadcrumb from '../layout/AppBreadcrumb.vue'
import ChatComposer from './ChatComposer.vue'
import WebSourceSnapshot from './WebSourceSnapshot.vue'
import UrgencyBanner from '../health/UrgencyBanner.vue'
import CrisisCard from '../mind/CrisisCard.vue'
import EmotionCard from '../mind/EmotionCard.vue'
import SafetyPlanCard from '../mind/SafetyPlanCard.vue'

const props = defineProps<{ agent: Agent }>()
const ui = useOverlay(), body = ref<HTMLElement>(), store = useMindChatStore()
const { busy, error, latest } = storeToRefs(store)
const workflowLabels: Record<string, string> = {
  understand: '正在听你说', assess_mind: '正在梳理情绪与风险', crisis: '正在整理可以立刻获得的帮助',
  boundary: '正在整理陪伴的边界', clarify: '正在整理想了解的情况', retrieve: '正在查找心理关怀资料',
  web_search: '正在查找官方资料', generate: '正在组织回应', validate: '正在检查表达是否合适',
  verify_grounding: '正在核对建议与原文', insufficient: '正在整理资料不足的说明',
  supportive_fallback: '正在整理陪伴建议', completed: '回应已完成', failed: '本次回应未完成',
}
const progressLabel = computed(() => store.loading ? '正在加载会话' : workflowLabels[store.stage || store.turns.at(-1)?.stage || 'understand'] || '正在处理')
const webSnapshot = ref<WebSource | null>(null)
const configuration = ref<MindConfig | null>(null), configError = ref('')

const messages = computed(() => store.turns.flatMap(turn => [
  { role: 'user' as const, text: turn.question, turnId: turn.id, failed: false, response: undefined as MindAnswer | undefined },
  ...(turn.response
    ? [{ role: 'assistant' as const, text: turn.response.answer, turnId: turn.id, failed: false, response: turn.response as MindAnswer | undefined }]
    : turn.status === 'failed'
      ? [{ role: 'assistant' as const, text: turn.error || '上次回应未完成，未保存最终内容。', turnId: turn.id, failed: true, response: undefined as MindAnswer | undefined }]
      : []),
]))
const retrieved = computed<LocalCitation[]>(() => (latest.value?.retrieved_hits || []).map((hit, index) => ({ index: index + 1, hit })))
const latestTurn = computed(() => store.turns.find(turn => turn.id === store.evidenceTurnId))

async function loadConfig() {
  try { configuration.value = await mindApi.config(); configError.value = '' }
  catch (e) { configError.value = e instanceof Error ? e.message : '配置加载失败' }
}
onMounted(() => { void loadConfig(); void store.initialize() })
onUnmounted(() => store.stop())
watch(() => messages.value.length, async () => { await nextTick(); if (body.value) body.value.scrollTop = body.value.scrollHeight })
watch(() => store.active?.id, () => { webSnapshot.value = null })

function send(question: string) { void store.send(question) }
function retry() { if (configError.value) void loadConfig(); else void store.retry() }
function clear() {
  if (!busy.value && store.active) ui.confirm('删除会话', '删除当前会话及其保存的对话与风险快照？这些内容不会被找回。', () => { void store.remove() }, '删除')
}
function parts(text: string) { return text.split(/(【\d+】)/g) }
function citationIndex(text: string) { return /^【\d+】$/.test(text) ? Number(text.slice(1, -1)) : 0 }
function open(citation: MindCitation, response: MindAnswer, items: MindCitation[] = response.citations) {
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
  ui.open({ kind: 'chunk', title: '心理关怀资料依据', chunk: chunk(citation), doc: doc(citation), chunks: locals.map(chunk), documents: locals.map(doc), index: locals.findIndex(item => item.index === citation.index) })
}
function cite(index: number, response?: MindAnswer) { const citation = response?.citations.find(item => item.index === index); if (citation && response) open(citation, response) }
function answerLabel(response: MindAnswer) {
  if (response.status === 'crisis') return '现在需要立即获得支持'
  if (response.status === 'boundary') return '陪伴的边界'
  if (response.status === 'clarification') return '想多了解一点'
  if (response.status === 'insufficient') return '资料不足'
  return '陪伴与建议'
}
function checkLabel(response: MindAnswer) {
  if (!response.answer_checks) return ''
  if (response.answer_checks.status === 'error') return '检查未完成'
  if (response.answer_checks.status === 'blocked') return '表达未通过检查'
  if (response.answer_checks.status === 'partial') return '部分内容未通过检查'
  return '通过'
}
</script>

<template>
  <div class="page">
    <AppBreadcrumb />
    <div class="card agent-head" :style="{ '--tint': props.agent.tint, '--c': props.agent.color }">
      <span class="agent-ico"><AppIcon :name="props.agent.icon" :size="26" /></span>
      <div class="agent-id">
        <h1>心灵陪伴 <span class="badge green">情绪支持</span></h1>
        <p>情绪疏导与社交连接 · 丧亲与睡眠困扰 · 危机时优先给出可立刻获得的帮助</p>
      </div>
      <div class="agent-actions">
        <button class="btn sm" :disabled="busy || store.unconfirmed" @click="store.create">新建会话</button>
        <button class="btn sm" :disabled="busy || !store.active || store.unconfirmed" @click="clear">删除会话</button>
      </div>
    </div>

    <div class="agent-layout">
      <section class="card chat-panel" :aria-busy="busy">
        <div class="chat-head">
          <b>对话</b><span class="badge violet">情绪支持</span>
          <span class="chat-head-right">{{ configuration?.model || '模型配置加载中' }}</span>
        </div>
        <div class="session-controls">
          <label for="mind-session">历史会话</label>
          <AppSelect id="mind-session" class="select" :value="store.active?.id || ''" :disabled="busy || store.unconfirmed" @change="store.select(String($event))">
            <option disabled value="">{{ store.sessions.length ? '请选择会话' : '尚无历史会话，发送消息后自动创建' }}</option>
            <option v-if="store.active && !store.sessions.some(s => s.id === store.active?.id)" :value="store.active.id">{{ store.active.title }}</option>
            <option v-for="session in store.sessions" :key="session.id" :value="session.id">{{ session.title }}</option>
          </AppSelect>
          <button v-if="store.sessions.length < store.total" class="btn sm" :disabled="busy" @click="store.moreSessions">更多会话</button>
        </div>
        <p class="src-meta">
          情绪风险与危机处置由程序规则判断，对话与当次依据会保存在本机数据库；涉及伤害自己的想法时会优先给出热线与求助路径。
          {{ configuration?.web_configured ? '联网检索已配置，按需查询官方资料。' : '联网检索未配置，当前使用本地资料。' }}
        </p>

        <div ref="body" class="chat-body" aria-live="polite">
          <button v-if="store.hasMore" class="btn sm" :disabled="busy" @click="store.older">加载更早的对话</button>
          <div v-if="!messages.length" class="msg">
            <div class="bubble">你好，我是心灵陪伴。你可以说说最近的心情、睡眠、和家人的相处，或者只是想说说话。如果你现在有伤害自己的想法，请先拨打 120 或心理援助热线 12356，让身边的人陪着你。</div>
          </div>
          <div v-for="(message, index) in messages" :key="index" class="msg" :class="{ user: message.role === 'user' }">
            <div class="msg-main">
              <div class="msg-head">
                <b>{{ message.role === 'user' ? '我' : '心灵陪伴' }}</b>
                <button v-if="message.failed && store.turns.at(-1)?.id === message.turnId" class="link-btn" :disabled="busy" @click="retry">重试本条</button>
                <button v-if="message.response" class="link-btn" :aria-pressed="store.evidenceTurnId === message.turnId" @click="store.evidenceTurnId = message.turnId">查看本次依据</button>
                <span v-if="message.response">{{ answerLabel(message.response) }}</span>
              </div>
              <div class="bubble">
                <CrisisCard v-if="message.response?.status === 'crisis'" :notice="message.response.crisis_notice" />
                <UrgencyBanner
                  v-else-if="message.response && (message.response.urgency === 'L1' || message.response.urgency === 'L2')"
                  :urgency="message.response.urgency" :status="message.response.status"
                  :red-flags="message.response.red_flags_observed" :required-action="message.response.required_action" />
                <EmotionCard v-if="message.response?.signals.length || message.response?.screening" :signals="message.response?.signals || []" :screening="message.response?.screening" :risk-level="message.response?.risk_level" />
                <SafetyPlanCard v-if="message.response?.safety_plan.length" :steps="message.response.safety_plan" />
                <div class="msg-text">
                  <p v-if="message.response?.coverage === 'partial'" class="partial-answer-label">已核对到的部分</p>
                  <p v-for="(paragraph, paragraphIndex) in message.text.split('\n').filter(Boolean)" :key="paragraphIndex">
                    <template v-for="(part, partIndex) in parts(paragraph)" :key="partIndex">
                      <button v-if="citationIndex(part) && message.response?.citations.some(c => c.index === citationIndex(part))" class="link-btn" :aria-label="`查看心理关怀依据 ${citationIndex(part)}`" @click="cite(citationIndex(part), message.response)">{{ part }}</button>
                      <template v-else>{{ part }}</template>
                    </template>
                  </p>
                  <section v-if="message.response?.route_suggestion" class="route-hint" aria-label="转接建议">
                    <b>可以转接其他管家</b>
                    <p>{{ message.response.route_suggestion.reason }}</p>
                  </section>
                  <section v-if="message.response?.general_info?.length" class="general-concepts" aria-label="通用概念说明">
                    <b>通用概念说明</b>
                    <p v-for="(info, infoIndex) in message.response.general_info" :key="infoIndex">{{ info }}</p>
                  </section>
                </div>
              </div>
            </div>
          </div>
          <div v-if="busy" class="rag-status" role="status"><span class="spinner"></span>{{ progressLabel }}，请稍候…</div>
        </div>
        <div v-if="error || configError" class="document-error" role="alert">{{ error || configError }} <button class="btn sm" :disabled="busy" @click="retry">重试</button></div>
        <ChatComposer :context-key="store.active?.id || ''" placeholder="例如：最近总是睡不好，心里空落落的…" :busy="busy || store.unconfirmed || !configuration?.configured" @send="send" />
        <p v-if="configuration && !configuration.configured" class="document-error">请在后端配置聊天模型后再对话。</p>
        <p v-if="configuration && !configuration.enabled" class="document-error">心灵陪伴当前未启用，请在后端设置 MIND_ENABLED=true。</p>
      </section>

      <aside class="card src-panel mind-sources">
        <div class="src-head">
          <b>本次依据</b>
          <span class="badge blue">{{ retrieved.length }} 条本地片段 · {{ latest?.citations.length || 0 }} 条引用</span>
        </div>
        <p v-if="latestTurn" class="src-meta">{{ latestTurn.question }} · 保存于 {{ new Date(latestTurn.updated_at).toLocaleString('zh-CN') }} · 来源模型 {{ latest?.model }}，回放不重新核验。</p>
        <p class="src-meta" role="status">
          {{ !latest ? '对话后会展示识别到的情绪线索与召回资料。' : !latest.retrieval_log_id ? '本次未执行检索，请查看左侧的危机提示或陪伴边界。' : `已执行检索，范围内可用向量 ${latest.vector_count} 条，召回 ${retrieved.length} 条片段。` }}
        </p>
        <CrisisCard v-if="latest?.status === 'crisis'" :notice="latest.crisis_notice" />
        <EmotionCard v-if="latest?.signals.length || latest?.screening" :signals="latest?.signals || []" :screening="latest?.screening" :risk-level="latest?.risk_level" />
        <SafetyPlanCard v-if="latest?.safety_plan.length" :steps="latest.safety_plan" />
        <p v-if="latest?.answer_checks" class="src-meta">
          表达检查：{{ checkLabel(latest) || '通过' }} · 检查 {{ latest.answer_checks.checked_paragraphs }} 段，保留 {{ latest.answer_checks.accepted_paragraphs }} 段
        </p>
        <details v-if="latest?.metrics" class="src-meta">
          <summary>本次处理耗时 {{ (latest.metrics.total_ms / 1000).toFixed(1) }} 秒 · 模型调用 {{ latest.metrics.llm_calls }} 次</summary>
          <p v-for="(ms, stageName) in latest.metrics.stage_ms" :key="stageName">{{ workflowLabels[String(stageName)] || stageName }}：{{ (ms / 1000).toFixed(2) }} 秒</p>
        </details>
        <div class="src-list">
          <div v-if="!retrieved.length" class="src-empty">{{ latest?.retrieval_log_id ? '本次没有召回片段。' : '尚无检索结果。' }}</div>
          <button v-for="citation in retrieved" :key="citation.index" class="src-item" @click="open(citation, latest!, latest!.citations.length ? latest!.citations : retrieved)">
            <div class="src-item-top">
              <span class="src-idx">{{ citation.index }}</span>
              <span class="src-title">{{ citation.hit.doc_name }}</span>
              <span class="src-score">RRF {{ citation.hit.score.toFixed(6) }}</span>
            </div>
            <p class="src-snip">{{ citation.hit.text.slice(0, 100) }}…</p>
            <div class="src-foot2"><span>{{ citation.hit.source }}</span><span>第 {{ citation.hit.seq }} 段</span><span>{{ latest?.citations.some(c => c.index === citation.index) ? '答案已引用' : '仅检索命中' }}</span></div>
          </button>
        </div>
        <p class="src-meta">心灵陪伴提供情绪支持与心理教育信息，不构成诊断或治疗建议；如有伤害自己的想法，请立即拨打 120 或 12356。</p>
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
.mind-sources { min-width: 0; }
.mind-sources > .src-head { flex: 0 0 auto; flex-wrap: wrap; }
.mind-sources > .src-head .badge { max-width: 100%; white-space: normal; }
.mind-sources > .src-meta { flex: 0 0 auto; margin: 0; overflow-wrap: anywhere; }
.mind-sources > details.src-meta { max-height: 180px; overflow-y: auto; }
.mind-sources summary { cursor: pointer; line-height: 1.7; }
.mind-sources .src-list { min-height: 0; min-width: 0; overscroll-behavior: contain; }
.mind-sources .src-item { display: block; width: 100%; min-width: 0; box-sizing: border-box; text-align: left; }
.mind-sources .src-title { min-width: 0; overflow-wrap: anywhere; }
.mind-sources .src-foot2 { flex-wrap: wrap; justify-content: flex-start; gap: 4px 12px; line-height: 1.6; overflow-wrap: anywhere; }
</style>
