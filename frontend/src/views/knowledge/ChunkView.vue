<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
import { useDemoStore } from '../../stores/demo'
import { chunkText } from '../../demo/rag.js'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import ChunkPreviewList from '../../components/knowledge/ChunkPreviewList.vue'
import type { Chunk } from '../../types/models'
const store = useDemoStore(), s = store.state, router = useRouter()
const doc = computed(()=>s.docs.find(d=>d.id === s.chunkCfg.docId))
watchEffect(()=>{ if (!doc.value && s.docs.length) s.chunkCfg.docId=s.docs[0].id })
const preview = computed<Chunk[]>(()=>{ if (!doc.value) return []; const current = doc.value; let cursor=0; return chunkText(current.text,s.chunkCfg.size,s.chunkCfg.overlap).map((text:string,i:number)=>{ const idx=current.text.indexOf(text,Math.max(0,cursor-s.chunkCfg.overlap-8)); const start=idx<0?cursor:idx; cursor=start+text.length; return {id:`preview-${i}`,docId:current.id,index:i+1,text,chars:text.length,start,vectorized:false,vector:null} }) })
const avg = computed(()=>preview.value.length ? Math.round(preview.value.reduce((n,c)=>n+c.chars,0)/preview.value.length) : 0)
const committed = computed(()=>s.chunks.filter(c=>c.docId===doc.value?.id).length)
function next() { if (doc.value) { s.vecCfg.docId=doc.value.id; void router.push('/vector') } }
</script>
<template><div class="page"><AppBreadcrumb/><PageHeader title="文本切块" subtitle="把长文档切成语义完整的小段，是向量化与召回质量的关键一步。"><span class="badge" :class="committed?'green':'amber'">{{ committed ? `当前已保存 ${committed} 段` : '尚未保存切块结果' }}</span></PageHeader><div class="split-2"><div class="card cfg-card"><div class="field"><label for="chunkDoc">选择文档</label><select id="chunkDoc" v-model="s.chunkCfg.docId" class="select"><option v-for="d in s.docs.filter(d=>!d.parsing)" :key="d.id" :value="d.id">{{ d.name }}</option></select></div><div class="field"><label for="sizeRange">切块大小 <b><span id="sizeVal">{{ s.chunkCfg.size }}</span> 字符</b></label><input id="sizeRange" v-model.number="s.chunkCfg.size" type="range" min="100" max="500" step="10"><div class="hint">建议 200–300 字，兼顾语义完整与检索精度。</div></div><div class="field"><label for="ovRange">重叠长度 <b><span id="ovVal">{{ s.chunkCfg.overlap }}</span> 字符</b></label><input id="ovRange" v-model.number="s.chunkCfg.overlap" type="range" min="0" max="100" step="5"><div class="hint">相邻片段保留少量重叠，避免答案在边界处被截断。</div></div><div class="field"><label>快捷预设</label><div class="presets"><button v-for="p in [{label:'精细',size:150,overlap:30},{label:'标准',size:220,overlap:30},{label:'粗粒度',size:350,overlap:60}]" :key="p.size" class="chip" :class="{on:s.chunkCfg.size===p.size}" @click="s.chunkCfg.size=p.size;s.chunkCfg.overlap=p.overlap">{{ p.label }}</button></div></div><div class="hint-box"><AppIcon name="info" :size="14"/><div>按句号、问号、分号与换行优先切分；超长句按字符截断。点击「保存切块结果」后才会写入知识库。</div></div><button class="btn primary block lg" :disabled="!doc || doc.parsing || store.state.vectorBusy || store.state.busy" @click="doc && store.commitChunks(doc)"><AppIcon name="scissors" :size="15"/> 保存切块结果</button><button v-if="committed" class="btn block" style="margin-top:8px" @click="next"><AppIcon name="database" :size="14"/> 下一步：向量入库</button></div><div class="card"><div class="card-head"><b>切块预览</b><span id="chunkStat" class="sub">{{ doc ? `预计 ${preview.length} 段 · 平均 ${avg} 字` : '未选择文档' }}</span></div><ChunkPreviewList v-if="doc && preview.length" :chunks="preview" :doc="doc" :overlap="s.chunkCfg.overlap"/><EmptyState v-else icon="doc" :title="doc?'没有可切块的正文':'请选择一份文档'" :description="doc?'该文档可能为空或解析失败':'上传文档后即可预览切块效果'"/></div></div></div></template>
