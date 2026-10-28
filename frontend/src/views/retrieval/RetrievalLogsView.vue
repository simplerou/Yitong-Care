<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useDemoStore } from '../../stores/demo'
import { useOverlay } from '../../composables/useOverlay'
import type { RetrievalLog } from '../../types/models'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'
const store=useDemoStore(), ui=useOverlay(), router=useRouter()
const source=(h:RetrievalLog)=>store.state.docs.find(d=>d.id===h.results[0]?.chunk.docId)?.name || '—'
function replay(h:RetrievalLog) { store.state.search={q:h.q,results:h.results,took:h.took,scope:h.scope,topK:h.topK,threshold:h.threshold,ran:true}; void router.push('/search') }
function remove(id:string) { ui.confirm('删除检索记录','将删除这条检索记录，不影响知识库数据。',()=>{store.state.history=store.state.history.filter(h=>h.id!==id);store.notify('记录已删除')},'删除') }
function clear() { if (!store.state.history.length) {store.notify('暂无检索记录','warn');return} ui.confirm('清空检索记录','将清空本次会话中的全部检索记录，不影响知识库数据。',()=>{store.state.history=[];store.notify('检索记录已清空')},'清空') }
</script>
<template><div class="page"><AppBreadcrumb/><PageHeader title="检索记录" subtitle="保留每一次检索的查询词、召回数量与命中片段，便于回溯与效果评估。"><button class="btn" @click="clear"><AppIcon name="trash" :size="14"/> 清空记录</button></PageHeader><div class="card"><div class="card-head"><b>最近检索 <span class="badge">{{ store.state.history.length }}</span></b><span class="sub">本次会话内记录</span></div><div v-if="store.state.history.length" class="table-wrap"><table class="table"><thead><tr><th>检索内容</th><th>时间</th><th>命中数量</th><th>Top1 得分</th><th>Top1 来源</th><th style="text-align:right">操作</th></tr></thead><tbody><tr v-for="h in store.state.history" :key="h.id"><td class="q-cell" :title="h.q">{{ h.q }}</td><td class="muted num">{{ h.time }}</td><td class="num">{{ h.results.length }} 条</td><td class="num">{{ h.results[0]?.score.toFixed(2) || '—' }}</td><td class="muted" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ source(h) }}</td><td><div class="row-actions"><button class="link-btn" @click="replay(h)">查看结果</button><button class="link-btn danger" @click="remove(h.id)">删除</button></div></td></tr></tbody></table></div><EmptyState v-else icon="history" title="还没有检索记录" description="在「向量检索」中执行一次检索后，记录会自动保存在这里"/></div></div></template>
