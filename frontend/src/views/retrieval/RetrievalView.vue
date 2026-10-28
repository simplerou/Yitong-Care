<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDemoStore } from '../../stores/demo'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import RetrievalForm from '../../components/retrieval/RetrievalForm.vue'
import ResultCard from '../../components/retrieval/ResultCard.vue'
const store=useDemoStore(), route=useRoute()
watch(()=>route.query.q,q=>{if (typeof q === 'string' && q.trim()) store.search(q)},{immediate:true})
</script>
<template><div class="page"><AppBreadcrumb/><PageHeader title="向量检索" subtitle="输入自然语言问题，查看召回片段、相似度与原文出处。"><RouterLink class="btn" to="/records"><AppIcon name="history" :size="14"/> 检索记录</RouterLink></PageHeader><RetrievalForm/><div id="resultArea"><div v-if="!store.state.search.ran" class="card"><EmptyState icon="target" title="等待检索" description="输入问题后点击「检索」，这里会展示相似度最高的知识片段"/></div><div v-else-if="!store.state.search.results.length" class="card"><EmptyState icon="filter" title="没有命中达到阈值的内容" :description="`当前相似度阈值 ${store.state.search.threshold}，可尝试降低阈值或扩大知识范围`"/></div><template v-else><div class="result-summary"><span>找到 <b>{{ store.state.search.results.length }}</b> 条相关片段</span><span class="dot-sep"></span><span>检索耗时 <b>{{ store.state.search.took }}</b> ms</span><span class="dot-sep"></span><span>向量库 <b>{{ store.vectorCount }}</b> 条</span><span class="dot-sep"></span><span>TopK {{ store.state.search.topK }} · 阈值 {{ store.state.search.threshold }}</span></div><ResultCard v-for="(hit,i) in store.state.search.results" :key="hit.chunk.id" :hit="hit" :rank="i+1" :query="store.state.search.q" :top="store.state.search.results[0].score" :hits="store.state.search.results"/></template></div></div></template>
