<script setup lang="ts">
import { computed } from 'vue'
import { useDemoStore } from '../../stores/demo'
import { useOverlay } from '../../composables/useOverlay'
import { scorePct, snippetHTML } from '../../demo/rag.js'
import type { Hit } from '../../types/models'
const props=defineProps<{ hit: Hit; rank: number; query: string; top: number; hits: Hit[] }>(), store=useDemoStore(), ui=useOverlay()
const doc=computed(()=>store.state.docs.find(d=>d.id===props.hit.chunk.docId))
function open() { ui.open({kind:'chunk',title:'原文片段',chunk:props.hit.chunk,doc:doc.value,query:props.query,chunks:props.hits.map(h=>h.chunk),index:props.rank-1}) }
</script>
<template><div class="result"><span class="result-rank">{{ String(rank).padStart(2,'0') }}</span><div class="result-main"><div class="result-title"><span class="doc-name">{{ doc?.name || '未知文档' }}</span><span class="badge">第 {{ hit.chunk.index }} 段</span><span class="badge blue">{{ doc?.type || 'TXT' }}</span></div><p class="snippet" v-html="snippetHTML(hit.chunk.text,query)"></p><div class="result-meta"><span>来源：{{ doc?.source || '未知' }}</span><span>字符区间 {{ hit.chunk.start }}–{{ hit.chunk.start+hit.chunk.chars }}</span><span>{{ hit.chunk.chars }} 字</span><span>综合得分 {{ hit.score.toFixed(2) }} · 余弦 {{ hit.cos.toFixed(2) }}</span></div></div><div class="result-side"><div class="score-num">{{ scorePct(hit.score,top) }}<small>%</small></div><div class="score-bar"><i :style="{width:scorePct(hit.score,top)+'%'}"></i></div><button class="orig-btn" @click="open">查看原文</button></div></div></template>
