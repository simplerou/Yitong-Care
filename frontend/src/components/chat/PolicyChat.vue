<script setup lang="ts">
import { computed,nextTick,onMounted,onUnmounted,ref,watch } from 'vue'
import { storeToRefs } from 'pinia'
import { usePolicyChatStore } from '../../stores/policyChat'
import { policyApi,type PolicyAnswer,type PolicyCitation,type LocalCitation,type WebSource,safeWebUrl } from '../../api/chat'
import type { Agent,Chunk,KnowledgeDocument } from '../../types/models'
import { useOverlay } from '../../composables/useOverlay'
import AppBreadcrumb from '../layout/AppBreadcrumb.vue'
import ChatComposer from './ChatComposer.vue'
import WebSourceSnapshot from './WebSourceSnapshot.vue'
const props=defineProps<{agent:Agent}>(),ui=useOverlay(),body=ref<HTMLElement>(),store=usePolicyChatStore()
const {busy,error,latest}=storeToRefs(store)
const webSnapshot=ref<WebSource|null>(null)
const configuration=ref<{model:string;configured:boolean;knowledge_scope:string[];web_configured:boolean}|null>(null),configError=ref('')
const messages=computed(()=>store.turns.flatMap(turn=>[
 {role:'user',text:turn.question,turnId:turn.id,failed:false,response:undefined as PolicyAnswer|undefined},
 ...(turn.response?[{role:'assistant',text:turn.response.answer,turnId:turn.id,failed:false,response:turn.response}]:turn.status==='failed'?[{role:'assistant',text:turn.error||'上次任务未完成，未保存最终答案。',turnId:turn.id,failed:true,response:undefined}]:[])
]))
const retrieved=computed<LocalCitation[]>(()=>latest.value?.retrieved_hits?.map((hit,index)=>({index:index+1,hit}))||[])
async function loadConfig(){try{configuration.value=await policyApi.config();configError.value=''}catch(e){configError.value=e instanceof Error?e.message:'配置加载失败'}}
onMounted(()=>{void loadConfig();void store.initialize()})
onUnmounted(()=>store.stop())
watch(()=>messages.value.length,async()=>{await nextTick();if(body.value)body.value.scrollTop=body.value.scrollHeight})
watch(()=>store.active?.id,()=>{webSnapshot.value=null})
function send(question:string){void store.send(question)}
function retry(){if(configError.value)void loadConfig();else void store.retry()}
function clear(){if(!busy.value&&store.active)ui.confirm('删除会话','删除当前会话及其保存的问答和来源快照？知识库文档和检索记录不受影响。',()=>{void store.remove()},'删除')}
const diagnosticReasons:Record<string,string>={url_not_allowed:'非允许的官方链接或链接格式不安全',duplicate_search_url:'搜索链接重复',unexpected_extract_url:'提取返回了未请求的链接',duplicate_extract_url:'正文结果重复',empty_body:'网页正文为空',extraction_failed:'未成功返回该网页正文',region_mismatch:'地区不匹配',benefit_missing:'正文未包含所问补贴类别',topic_not_coincident:'养老主题与补贴内容不在相关段落中',specific_topic_missing:'缺少所问的具体养老主题',topic_missing:'缺少问题主题',output_limit:'相关，但已达到最终展示条数',relevant:'已保留'}
function reasonLabel(reason:string):string{return reason.startsWith('excerpt_')?'截取后的正文：'+reasonLabel(reason.slice(8)):diagnosticReasons[reason]||'格式或内容未满足要求'}
const stageLabels:Record<string,string>={not_started:'未开始',not_configured:'未配置',search:'搜索阶段中断',extract:'正文提取阶段中断',filter:'内容筛选阶段中断',complete:'处理完成'}
function parts(text:string){return text.split(/(【\d+】)/g)}
function citationIndex(text:string){return /^【\d+】$/.test(text)?Number(text.slice(1,-1)):0}
function open(citation:PolicyCitation,response:PolicyAnswer,items:PolicyCitation[]=response.citations){
 if(citation.source_type==='web'){webSnapshot.value=citation.web;return}
 const locals=items.filter((c):c is LocalCitation=>c.source_type!=='web'&&!!c.hit)
 const chunk=(c:LocalCitation):Chunk=>({id:`server-${c.hit.chunk_id}`,docId:c.hit.doc_id,index:c.hit.seq,text:c.hit.text,chars:c.hit.chars,start:c.hit.start,vectorized:true,vector:null})
 const doc=(c:LocalCitation):KnowledgeDocument=>({id:c.hit.doc_id,name:c.hit.doc_name,kbId:c.hit.kb_id,type:c.hit.type,size:'—',uploadAt:'—',source:c.hit.source,text:c.hit.text,status:'vectorized',parsing:false,persisted:true})
 ui.open({kind:'chunk',title:'政策原文依据',chunk:chunk(citation),doc:doc(citation),chunks:locals.map(chunk),documents:locals.map(doc),index:locals.findIndex(c=>c.index===citation.index)})
}
function cite(index:number,response?:PolicyAnswer){const citation=response?.citations.find(c=>c.index===index);if(citation&&response)open(citation,response)}
</script>
<template><div class="page"><AppBreadcrumb/>
<div class="card agent-head" :style="{'--tint':props.agent.tint,'--c':props.agent.color}"><span class="agent-ico"><AppIcon name="doc" :size="26"/></span><div class="agent-id"><h1>政策顾问 <span class="badge green">知识库问答</span></h1><p>养老政策解释与办理咨询 · 回答附原文依据</p></div><div class="agent-actions"><button class="btn sm" :disabled="busy||store.unconfirmed" @click="store.create">新建会话</button><button class="btn sm" :disabled="busy||!store.active||store.unconfirmed" @click="clear">删除会话</button></div></div>
<div class="agent-layout"><section class="card chat-panel" :aria-busy="busy"><div class="chat-head"><b>对话</b><span class="badge violet">RAG 增强</span><span class="chat-head-right">{{configuration?.model||'模型配置加载中'}}</span></div>
<div class="session-controls"><label for="policy-session">历史会话</label><select id="policy-session" class="select" :value="store.active?.id||''" :disabled="busy||store.unconfirmed" @change="store.select(($event.target as HTMLSelectElement).value)"><option disabled value="">{{store.sessions.length?'请选择会话':'尚无历史会话，发送问题后自动创建'}}</option><option v-if="store.active&&!store.sessions.some(s=>s.id===store.active?.id)" :value="store.active.id">{{store.active.title}}</option><option v-for="session in store.sessions" :key="session.id" :value="session.id">{{session.title}}</option></select><button v-if="store.sessions.length<store.total" class="btn sm" :disabled="busy" @click="store.moreSessions">更多会话</button></div>
<p class="src-meta">范围：{{configuration?.knowledge_scope.join(' / ')||'尚未加载'}} · 问答与当次来源已保存到数据库，历史回放不会重新调用模型。{{configuration?.web_configured?'联网搜索已配置，按需查询官方资料。':'联网搜索未配置，当前使用本地资料。'}}</p>
<div ref="body" class="chat-body" aria-live="polite"><button v-if="store.hasMore" class="btn sm" :disabled="busy" @click="store.older">加载更早的问答</button><div v-if="!messages.length" class="msg"><div class="bubble">您好，我是政策顾问。可以咨询长期护理保险、养老补贴和适老化改造政策。涉及当地条件时，请说明所在地区；我会根据已入库资料回答。</div></div>
<div v-for="(message,i) in messages" :key="i" class="msg" :class="{user:message.role==='user'}"><div class="msg-main"><div class="msg-head"><b>{{message.role==='user'?'我':'政策顾问'}}</b><button v-if="message.failed&&store.turns.at(-1)?.id===message.turnId" class="link-btn" :disabled="busy" @click="retry">重试本条</button><button v-if="message.response" class="link-btn" :aria-pressed="store.evidenceTurnId===message.turnId" @click="store.evidenceTurnId=message.turnId">查看本次依据</button><span v-if="message.response">{{message.response.answer_checks?.status==='error'?'检查未完成':message.response.answer_checks?.status==='blocked'?'依据未通过检查':message.response.status==='clarification'?'需要补充信息':message.response.status==='insufficient'?'资料不足':'依据资料回答'}}</span></div><div class="bubble"><div class="msg-text"><p v-for="(paragraph,j) in message.text.split('\n').filter(Boolean)" :key="j"><template v-for="(part,k) in parts(paragraph)" :key="k"><button v-if="citationIndex(part)&&message.response?.citations.some(c=>c.index===citationIndex(part))" class="link-btn" :aria-label="`查看政策依据 ${citationIndex(part)}`" @click="cite(citationIndex(part),message.response)">{{part}}</button><template v-else>{{part}}</template></template></p><p v-if="message.response?.answer_checks" class="muted">原文一致性辅助检查：保留 {{message.response.answer_checks.accepted_paragraphs}} / {{message.response.answer_checks.checked_paragraphs}} 段，仍请核对原文。</p></div></div></div></div>
<div v-if="busy" class="rag-status" role="status"><span class="spinner"></span>正在分析问题、检索资料，必要时查询官方网页，请稍候…</div>
</div><div v-if="error||configError" class="document-error" role="alert">{{error||configError}} <button class="btn sm" :disabled="busy" @click="retry">重试</button></div>
<ChatComposer placeholder="例如：杭州市长期护理保险如何申请？" :busy="busy||store.unconfirmed||!configuration?.configured" @send="send"/><p v-if="configuration&&!configuration.configured" class="document-error">请在后端配置聊天模型后再提问。</p></section>
<aside class="card src-panel policy-sources"><div class="src-head"><b>问答依据快照</b><span class="badge blue">{{retrieved.length}} 条本地片段 · {{latest?.web_sources?.length||0}} 条网页 · {{latest?.citations.length||0}} 条引用</span></div>
<p v-if="latest" class="src-meta">{{store.turns.find(t=>t.id===store.evidenceTurnId)?.question}} · 保存于 {{new Date(store.turns.find(t=>t.id===store.evidenceTurnId)?.updated_at||'').toLocaleString('zh-CN')}} · 来源模型 {{latest.model}}，回放不重新核验政策。</p><p class="src-meta" role="status">{{!latest?'提问后展示实际召回的政策片段。':!latest.retrieval_log_id?'本次尚未执行检索，请查看左侧的追问或服务范围说明。':`已执行检索，范围内可用向量 ${latest.vector_count} 条，召回 ${retrieved.length} 条片段。召回不等于已被答案引用。`}}</p>
<p v-if="latest?.web_status&&latest.web_status!=='not_used'" class="src-meta" role="status">{{latest.web_status==='success'?'已联网获取官方网页正文；仍需核对适用条件及后续政策变化。':latest.web_warning}}</p>
<details v-if="latest?.web_diagnostics" class="src-meta"><summary>联网过程：搜索 {{latest.web_diagnostics.search_count}} 条 → 获得正文 {{latest.web_diagnostics.body_count}} 条 → 保留 {{latest.web_diagnostics.accepted_count}} 条</summary><p>{{stageLabels[latest.web_diagnostics.stage]||'处理中'}} · 官方候选 {{latest.web_diagnostics.official_count}} 条 · 请求提取 {{latest.web_diagnostics.extraction_requested}} 条 · 提取返回 {{latest.web_diagnostics.extraction_returned}} 条</p><p v-for="(count,reason) in latest.web_diagnostics.rejected_counts" :key="reason">{{reasonLabel(String(reason))}}：{{count}} 条</p><div v-for="page in latest.web_diagnostics.pages" :key="page.url" style="margin-bottom:12px;overflow-wrap:anywhere"><a :href="safeWebUrl(page.url)||undefined" target="_blank" rel="noopener noreferrer">{{page.title}}</a><p>{{page.outcome==='accepted'?'保留':'未采用'}} · {{reasonLabel(page.reason)}}</p></div></details>
<div v-if="latest?.policy_categories?.length" class="src-meta">政策类别：{{latest.policy_categories.join(' / ')}}</div><div v-if="latest?.citations.length" class="src-meta">回答引用：<button v-for="citation in latest.citations" :key="citation.index" class="link-btn" @click="open(citation,latest!)">【{{citation.index}}】</button></div>
<div class="src-list"><div v-if="!retrieved.length" class="src-empty">{{latest?.retrieval_log_id?'本次没有召回片段。请根据左侧说明核对入库状态或知识范围。':'尚无检索结果。'}}</div><button v-for="citation in retrieved" :key="citation.index" class="src-item" @click="open(citation,latest!,retrieved)"><div class="src-item-top"><span class="src-idx">{{citation.index}}</span><span class="src-title">{{citation.hit.doc_name}}</span><span class="src-score">RRF {{citation.hit.score.toFixed(6)}}</span></div><p class="src-snip">{{citation.hit.text.slice(0,100)}}…</p><div class="src-foot2"><span>{{citation.hit.source}}</span><span>第 {{citation.hit.seq}} 段</span><span>{{latest?.citations.some(c=>c.index===citation.index)?'答案已引用':'仅检索命中'}}</span></div></button>
<article v-for="(source,i) in latest?.web_sources||[]" :key="source.url" class="src-item web-source"><button type="button" class="web-snapshot-open" :aria-label="`查看保存的网页正文：${source.title}`" @click="webSnapshot=source"><div class="src-item-top"><span class="src-idx">{{retrieved.length+i+1}}</span><span class="src-title">{{source.title}}</span><span class="badge blue">网络正文</span></div><p class="src-snip">{{source.content.slice(0,140)}}…</p><p class="src-snip">{{source.is_truncated?`正文节选 ${source.content.length} / ${source.original_content_chars} 字`:source.is_truncated===false?'已展示服务提取的正文':'正文片段'}} · 附件及全文完整性未核实</p><div class="src-foot2"><span>{{source.published_date?'发布日期：'+source.published_date:'发布日期待核实'}}</span><span>获取于 {{new Date(source.retrieved_at).toLocaleString('zh-CN')}}</span></div></button><a class="web-source-link" :href="safeWebUrl(source.url)||undefined" target="_blank" rel="noopener noreferrer"><span class="web-source-url" :title="source.url">{{source.url}}</span><span class="web-source-action">查看官网 ↗</span></a></article>
</div></aside></div><WebSourceSnapshot v-if="webSnapshot" :source="webSnapshot" @close="webSnapshot=null"/></div></template>

<style scoped>
.session-controls { display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:10px 16px; border-bottom:1px solid var(--line); }
.session-controls label { color:var(--muted); font-size:12px; }
.session-controls select { min-width:0; flex:1 1 200px; max-width:100%; }

.policy-sources { min-width: 0; }
.policy-sources > .src-head { flex: 0 0 auto; flex-wrap: wrap; }
.policy-sources > .src-head .badge { max-width: 100%; white-space: normal; }
.policy-sources > .src-meta { flex: 0 0 auto; margin: 0; overflow-wrap: anywhere; }
.policy-sources > details.src-meta { max-height: 180px; overflow-y: auto; }
.policy-sources summary { cursor: pointer; line-height: 1.7; }
.policy-sources .src-list { min-height: 0; min-width: 0; overscroll-behavior: contain; }
.policy-sources .src-item { display: block; width: 100%; min-width: 0; box-sizing: border-box; text-align: left; }
.policy-sources .src-item-top { min-width: 0; }
.policy-sources .src-title { min-width: 0; overflow-wrap: anywhere; }
.policy-sources .src-item-top > .badge { flex: 0 0 auto; }
.policy-sources .src-foot2 { flex-wrap: wrap; justify-content: flex-start; gap: 4px 12px; line-height: 1.6; overflow-wrap: anywhere; }
.web-snapshot-open { display:block; width:100%; min-width:0; border:0; padding:0; text-align:left; color:inherit; background:transparent; font:inherit; cursor:pointer; }
.web-source { color: inherit; text-decoration: none; }
.web-source .src-snip { overflow-wrap: anywhere; }
.web-source-link { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 10px; padding-top: 8px; margin-top: 8px; border-top: 1px solid var(--line); font-size: 11px; line-height: 1.6; text-decoration:none; }
.web-source-url { min-width: 0; flex: 1 1 180px; color: var(--muted); overflow-wrap: anywhere; }
.web-source-action { flex: 0 0 auto; color: var(--brand); font-weight: 600; }
@media (max-width: 600px) {
  .policy-sources .src-item-top { flex-wrap: wrap; }
  .policy-sources .src-title { flex-basis: calc(100% - 30px); }
  .policy-sources .src-item-top > .badge { margin-left: 25px; }
}
</style>
