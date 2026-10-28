<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useRetrievalStore } from '../../stores/retrieval'
import { useOverlay } from '../../composables/useOverlay'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'
const store=useRetrievalStore(),ui=useOverlay(),router=useRouter()
onMounted(()=>{void store.loadLogs()})
async function replay(id:string){if(await store.replay(id))void router.push('/search')}
function remove(id?:string){ui.confirm(id?'删除检索记录':'清空检索记录',id?'将删除这次检索及其结果快照，不影响知识库数据。':'将清空全部检索记录和历史结果快照，不影响知识库数据。',()=>{void store.remove(id)},id?'删除':'清空')}
function page(delta:number){store.page+=delta;void store.loadLogs()}
</script>
<template><div class="page"><AppBreadcrumb/><PageHeader title="检索记录" subtitle="检索记录和结果快照保存在数据库中，刷新后仍可回放。"><button class="btn" :disabled="!!store.busyId||!store.total" @click="remove()"><AppIcon name="trash" :size="14"/>清空记录</button></PageHeader><div v-if="store.logsError" class="knowledge-error" role="alert"><span>{{store.logsError}}</span><button class="btn sm" @click="store.loadLogs">重试</button></div><div class="card" :aria-busy="store.loading"><div class="card-head"><b>最近检索 <span class="badge">{{store.total}}</span></b><span class="sub">已持久化到数据库</span></div><div v-if="store.loading" class="knowledge-loading" role="status">正在加载记录…</div><div v-else-if="store.records.length" class="table-wrap"><table class="table"><thead><tr><th>检索内容</th><th>时间</th><th>命中数量</th><th>Top1 得分</th><th>Top1 来源</th><th style="text-align:right">操作</th></tr></thead><tbody><tr v-for="h in store.records" :key="h.id"><td class="q-cell" :title="h.query">{{h.query}}</td><td class="muted num">{{new Date(h.created_at).toLocaleString('zh-CN',{hour12:false})}}</td><td class="num">{{h.hit_count}} 条</td><td class="num">{{h.top_score?.toFixed(6)||'—'}} {{h.strategy==='bm25_rrf'?'RRF':'历史加权'}}</td><td class="muted" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{h.top_source||'—'}}</td><td><div class="row-actions"><button class="link-btn" :disabled="!!store.busyId" @click="replay(h.id)">查看结果</button><button class="link-btn danger" :disabled="!!store.busyId" @click="remove(h.id)">删除</button></div></td></tr></tbody></table></div><EmptyState v-else-if="!store.logsError" icon="history" title="还没有检索记录" description="执行一次真实检索后，记录会自动保存在这里。"/><div v-if="store.total>20" class="document-pagination"><span>第 {{store.page}} / {{Math.ceil(store.total/20)}} 页</span><button class="btn sm" :disabled="store.page<=1||store.loading" @click="page(-1)">上一页</button><button class="btn sm" :disabled="store.page*20>=store.total||store.loading" @click="page(1)">下一页</button></div></div></div></template>
