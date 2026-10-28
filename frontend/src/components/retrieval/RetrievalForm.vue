<script setup lang="ts">
import { onMounted,ref } from 'vue'
import { useRetrievalStore } from '../../stores/retrieval'
import { useKnowledgeStore } from '../../stores/knowledge'
import { embeddingsApi,type EmbeddingModel } from '../../api/embeddings'
const store=useRetrievalStore(),knowledge=useKnowledgeStore(),model=ref<EmbeddingModel|null>(null),loadError=ref('')
const examples=['社区助餐如何登记？','长期护理保险怎么申请？','居家防跌倒需要注意什么？']
onMounted(async()=>{
 try{const [metadata]=await Promise.all([embeddingsApi.models(),knowledge.loadChoices()]);model.value=metadata.models[0]||null}
 catch(e){loadError.value=e instanceof Error?e.message:'检索配置加载失败。'}
})
</script>
<template><form class="card search-hero" @submit.prevent="store.search()"><div class="search-box"><div class="search-input-wrap"><AppIcon name="search" :size="19"/><input id="searchInput" v-model="store.parameters.query" maxlength="1000" :disabled="store.searching" aria-label="输入问题或关键词" placeholder="输入问题或关键词，检索已入库的真实文档"></div><button type="submit" class="btn primary lg" :disabled="store.searching||!model?.configured" style="height:48px;padding:0 26px"><AppIcon name="search" :size="16"/>{{store.searching?'检索中…':'检索'}}</button></div>
<div class="search-opts"><label class="opt">知识范围<select id="scopeSel" v-model="store.parameters.scope" class="select" :disabled="store.searching"><option value="all">全部知识库</option><option v-if="store.result?.historical&&store.parameters.scope!=='all'&&!knowledge.choices.some(d=>d.id===store.parameters.scope)" :value="store.parameters.scope">历史文档（已删除）</option><option v-for="d in knowledge.choices" :key="d.id" :value="d.id">{{d.name}}</option></select></label><label class="opt">TopK<select id="topKSel" v-model.number="store.parameters.top_k" class="select" style="min-width:74px" :disabled="store.searching"><option v-for="n in [3,5,10]" :key="n" :value="n">{{n}}</option></select></label><label class="opt">语义余弦下限<input id="thrRange" v-model.number="store.parameters.threshold" type="range" min="0.02" max="0.6" step="0.01" :disabled="store.searching"><b>{{Number(store.parameters.threshold).toFixed(2)}}</b></label><span class="opt" style="margin-left:auto"><AppIcon name="database" :size="13"/>{{model?.name||'加载模型信息…'}} · {{model?.dimensions||'—'}} 维</span></div>
<div v-if="loadError||model?.hint" class="document-error" role="alert">{{loadError||model?.hint}}</div><p class="muted">Embedding + BM25 + RRF；余弦下限仅影响语义召回，BM25 独立召回。</p><div class="search-examples">试试：<button v-for="q in examples" :key="q" type="button" class="chip" :disabled="store.searching||!model?.configured" @click="store.search(q)">{{q}}</button></div></form></template>
