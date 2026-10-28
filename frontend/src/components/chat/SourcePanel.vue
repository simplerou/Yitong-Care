<script setup lang="ts">
import { computed } from 'vue'
import { useDemoStore } from '../../stores/demo'
import { useOverlay } from '../../composables/useOverlay'
import { highlight, scorePct } from '../../demo/rag.js'
import type { Agent, Hit } from '../../types/models'
const props=defineProps<{agent:Agent}>(), store=useDemoStore(), ui=useOverlay()
const hits=computed(()=>store.state.lastHits[props.agent.id] || [])
const doc=(hit:Hit)=>store.state.docs.find(d=>d.id===hit.chunk.docId)
function open(hit:Hit,index:number) {ui.open({kind:'chunk',title:'原文片段',chunk:hit.chunk,doc:doc(hit),chunks:hits.value.map(h=>h.chunk),index,query:store.state.lastQuery[props.agent.id] || ''})}
</script>
<template><aside class="card src-panel"><div class="src-head"><b>参考知识</b><span class="badge blue">RAG</span><span class="chat-head-right" style="margin-left:auto">最近一次检索 · 命中 <b id="srcHitCount" style="color:var(--brand);margin:0 2px">{{ hits.length }}</b> 条</span></div><div class="src-meta">检索范围：{{ agent.kbNames.join(' / ') }}</div><div id="srcList" class="src-list"><div v-if="!hits.length" class="src-empty"><div class="mini-ico"><AppIcon name="layers" :size="20"/></div>还没有检索结果<br>向 {{ agent.name }} 提问后，这里会展示命中的知识片段与原文出处</div><button v-for="(hit,i) in hits" :key="hit.chunk.id" class="src-item" @click="open(hit,i)"><div class="src-item-top"><span class="src-idx">{{ i+1 }}</span><span class="src-title">{{ doc(hit)?.name || '未知文档' }}</span><span class="src-score">{{ scorePct(hit.score,hits[0].score) }}%</span></div><p class="src-snip"><span v-html="highlight(hit.chunk.text.slice(0,90),store.state.lastQuery[agent.id] || '')"></span>…</p><div class="src-foot2"><span>第 {{ hit.chunk.index }} 段</span><span>{{ hit.chunk.chars }} 字</span><span>{{ doc(hit)?.type }}</span></div></button></div></aside></template>
