<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useDemoStore } from '../../stores/demo'
import { useOverlay } from '../../composables/useOverlay'
import StatusTag from '../common/StatusTag.vue'
import type { KnowledgeDocument } from '../../types/models'
defineProps<{ documents: KnowledgeDocument[] }>()
const store = useDemoStore(), router = useRouter(), ui = useOverlay()
const chunks = (id: string) => store.state.chunks.filter(c => c.docId === id)
function go(id: string, vector = false) { if (vector) store.state.vecCfg.docId = id; else store.state.chunkCfg.docId = id; void router.push(vector ? '/vector' : '/chunk') }
</script>
<template><div class="table-wrap"><table class="table"><thead><tr><th>文档名称</th><th>类型</th><th>大小</th><th>已切块</th><th>状态</th><th>上传时间</th><th style="text-align:right">操作</th></tr></thead><tbody><tr v-for="d in documents" :key="d.id"><td><div class="name"><span class="doc-ico"><AppIcon name="doc" :size="15"/></span><div><div>{{ d.name }}</div><div class="meta-cell">{{ d.source || '本地上传' }}</div></div></div></td><td><span class="badge">{{ d.type }}</span></td><td class="muted num">{{ d.size }}</td><td class="num">{{ chunks(d.id).length ? `${chunks(d.id).length} 段` : '—' }}</td><td><StatusTag :doc="d"/></td><td class="muted num">{{ d.uploadAt }}</td><td><div class="row-actions"><button class="link-btn" @click="ui.open({kind:'document',title:'文档详情',subtitle:d.name,doc:d})">查看</button><button class="link-btn" :disabled="d.parsing" @click="go(d.id)">切块</button><button class="link-btn" :disabled="!chunks(d.id).length || d.parsing" :title="!chunks(d.id).length ? '请先保存切块结果' : '向量入库'" :style="!chunks(d.id).length ? {opacity:.4} : {}" @click="go(d.id,true)">入库</button><button class="link-btn danger" @click="ui.confirm('删除文档',`将删除「${d.name}」及其全部文本块与向量，且不可恢复。`,()=>store.removeDocument(d.id),'确认删除')">删除</button></div></td></tr><tr v-if="!documents.length"><td colspan="7" style="text-align:center;padding:30px">没有匹配的文档，请尝试其他名称。</td></tr></tbody></table></div></template>
