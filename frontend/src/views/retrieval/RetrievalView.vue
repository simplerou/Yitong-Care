<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { useRetrievalStore } from '../../stores/retrieval'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import RetrievalForm from '../../components/retrieval/RetrievalForm.vue'
import ResultCard from '../../components/retrieval/ResultCard.vue'
const store=useRetrievalStore(),route=useRoute()
watch(()=>route.fullPath,()=>{
 const q=route.query.q
 if(typeof q==='string'&&q.trim()){Object.assign(store.parameters,{scope:'all',top_k:5,threshold:.12});void store.search(q)}
},{immediate:true})
</script>
<template><div class="page"><AppBreadcrumb/><PageHeader title="向量检索" subtitle="使用已入库的真实文档进行语义与关键词混合检索，并查看原文出处。"><RouterLink class="btn" to="/records"><AppIcon name="history" :size="14"/>检索记录</RouterLink></PageHeader><RetrievalForm/>
<div v-if="store.error" class="knowledge-error" role="alert"><span>{{store.error}}</span><button class="btn sm" :disabled="store.searching" @click="store.search()">重试</button></div>
<div v-if="store.result?.historical" class="hint-box" style="margin-bottom:14px"><AppIcon name="history" :size="14"/><div>当前为历史检索快照，保留当时的片段与得分。需要最新结果时请重新检索。</div></div>
<div id="resultArea" :aria-busy="store.searching"><div v-if="store.searching" class="card knowledge-loading" role="status"><span class="spinner"></span>正在生成问题向量并检索资料…</div><div v-else-if="!store.result&&!store.error" class="card"><EmptyState icon="target" title="等待检索" description="请先完成向量入库，再输入问题检索真实知识片段。"/></div><div v-else-if="store.result&&!store.result.hits.length" class="card"><EmptyState icon="filter" title="未召回相关片段" :description="store.result.vector_count?`当前阈值 ${store.result.threshold}，可降低阈值或扩大知识范围。`:'当前范围没有可检索向量，请先完成向量入库。'"/></div><template v-else-if="store.result"><div class="result-summary"><span>找到 <b>{{store.result.hits.length}}</b> 条相关片段</span><span class="dot-sep"></span><span>检索耗时 <b>{{store.result.took_ms}}</b> ms</span><span class="dot-sep"></span><span>范围内向量 <b>{{store.result.vector_count}}</b> 条</span><span class="dot-sep"></span><span>TopK {{store.result.top_k}} · {{store.result.strategy==='bm25_rrf'?'语义余弦下限':'历史综合阈值'}} {{store.result.threshold}}</span><span class="dot-sep"></span><span>模型 {{store.result.model.split('@')[0]}}</span></div><ResultCard v-for="(hit,i) in store.result.hits" :key="hit.chunk_id" :strategy="store.result.strategy" :hit="hit" :rank="i+1" :query="store.result.query" :hits="store.result.hits"/></template></div></div></template>
