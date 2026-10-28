<script setup lang="ts">
import { useOverlay } from '../../composables/useOverlay'
import { snippetHTML } from '../../demo/rag.js'
import type { SearchHit } from '../../api/retrieval'
import type { Chunk,KnowledgeDocument } from '../../types/models'
const props=defineProps<{hit:SearchHit;rank:number;query:string;hits:SearchHit[];strategy?:string}>(),ui=useOverlay()
const toChunk=(h:SearchHit):Chunk=>({id:`server-${h.chunk_id}`,docId:h.doc_id,index:h.seq,text:h.text,chars:h.chars,start:h.start,vectorized:true,vector:null})
const toDocument=(h:SearchHit):KnowledgeDocument=>({id:h.doc_id,kbId:h.kb_id,name:h.doc_name,type:h.type,size:'—',source:h.source,text:h.text,uploadAt:'—',status:'vectorized',parsing:false,persisted:true})
function open(){ui.open({kind:'chunk',title:'原文片段',chunk:toChunk(props.hit),doc:toDocument(props.hit),query:props.query,chunks:props.hits.map(toChunk),documents:props.hits.map(toDocument),index:props.rank-1})}
</script>
<template><div class="result"><span class="result-rank">{{String(rank).padStart(2,'0')}}</span><div class="result-main"><div class="result-title"><span class="doc-name">{{hit.doc_name}}</span><span class="badge">第 {{hit.seq}} 段</span><span class="badge blue">{{hit.type}}</span></div><p class="snippet" v-html="snippetHTML(hit.text,query)"></p><div class="result-meta"><span>来源：{{hit.source}}</span><span>字符区间 {{hit.start}}–{{hit.end}}</span><span>{{hit.chars}} 字</span><span>{{strategy==='bm25_rrf'?'RRF':'历史加权'}} {{hit.score.toFixed(6)}} · 余弦 {{hit.cos.toFixed(3)}} · {{strategy==='bm25_rrf'?'BM25':'历史词面'}} {{hit.lexical_score.toFixed(3)}}<template v-if="strategy==='bm25_rrf'"> · 语义排名 {{hit.semantic_rank??'未召回'}} · BM25 排名 {{hit.bm25_rank??'未召回'}}</template></span></div></div><div class="result-side"><div class="score-num" style="font-size:20px" :title="strategy==='bm25_rrf'?'RRF 排名融合得分，不代表概率或答案正确率':'历史加权相关度，不代表答案正确率'">{{hit.score.toFixed(6)}}<small>{{strategy==='bm25_rrf'?'RRF':'历史加权'}}</small></div><button class="orig-btn" @click="open">查看原文</button></div></div></template>
