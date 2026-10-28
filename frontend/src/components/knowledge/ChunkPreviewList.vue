<script setup lang="ts">
import { useOverlay } from '../../composables/useOverlay'
import type { Chunk, KnowledgeDocument } from '../../types/models'
const props = defineProps<{ chunks: Chunk[]; doc: KnowledgeDocument; overlap: number }>(), ui = useOverlay()
function open(index: number) { ui.open({kind:'preview',title:'切块预览',subtitle:props.doc.name,doc:props.doc,chunks:props.chunks,chunk:props.chunks[index],index}) }
</script>
<template><div id="chunkPreview" class="chunk-list"><button v-for="(c,i) in chunks" :key="i" class="chunk-row" @click="open(i)"><span class="chunk-no">{{ i+1 }}</span><div class="chunk-content"><div class="chunk-text">{{ c.text }}</div><div class="chunk-meta"><span>{{ c.chars }} 字</span><span>重叠 {{ c.overlapChars ?? overlap }} 字</span><span class="ok">点击查看全文</span></div></div></button></div></template>
