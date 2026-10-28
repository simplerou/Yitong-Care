<script setup lang="ts">
import { useRoute } from 'vue-router'
import { menuGroups } from '../../config/menu'
import { useKnowledgeStore } from '../../stores/knowledge'
import { useRetrievalStore } from '../../stores/retrieval'
import { useOverlay } from '../../composables/useOverlay'
const route = useRoute(), ui = useOverlay()
const knowledge = useKnowledgeStore(), retrieval = useRetrievalStore()
function count(name: unknown) { if (name === 'kb') return knowledge.error ? '—' : knowledge.stats.documents; if (name === 'chunk') return knowledge.error ? '—' : knowledge.stats.chunks; if (name === 'vector') return knowledge.error ? '—' : knowledge.stats.vectors; if (name === 'records') return retrieval.logsError ? '—' : retrieval.total; return null }
</script>
<template><aside id="sidebar" class="sidebar"><nav class="side-scroll" aria-label="主导航"><div v-for="group in menuGroups" :key="group.title" class="side-group"><div class="side-label">{{ group.title }}</div><RouterLink v-for="item in group.items" :key="item.path" class="nav-item" :class="{active: route.path === item.path}" :to="item.path" :style="{'--tint': String(item.meta?.tint || ''), '--c': String(item.meta?.color || '')}"><span class="nav-ico"><AppIcon :name="String(item.meta?.icon)" :size="16"/></span><span class="nav-txt">{{ item.meta?.title }}</span><span v-if="count(item.name) !== null" class="nav-num">{{ count(item.name) }}</span></RouterLink></div></nav><div class="side-foot"><div class="engine-card"><div class="engine-head"><span class="live-dot"></span>知识库管理</div><p>{{ knowledge.error ? '后端暂不可用' : `文档 ${knowledge.stats.documents} 份 · 文本块 ${knowledge.stats.chunks} 段` }}<br>真实知识检索 · 问答仍为演示</p><div class="engine-bars"><i v-for="n in 6" :key="n"></i></div></div><button class="side-help" @click="ui.open({kind:'help', title:'原型使用说明', subtitle:'颐养通 · 智能养老服务平台 v0.1'})"><AppIcon name="info" :size="13"/> 使用说明 / 菜单地图</button></div></aside></template>
