<script setup lang="ts">
import { computed } from 'vue'
import { agents } from '../../config/agents'
import { useDemoStore } from '../../stores/demo'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import PageHeader from '../../components/common/PageHeader.vue'
const store=useDemoStore(), all=computed(()=>store.services.slice(0,20))
const stats=computed(()=>[{label:'累计服务',value:all.value.length,unit:'次'},{label:'今日服务',value:store.services.filter(r=>r.time.startsWith('今天')).length,unit:'次'},{label:'引用原文',value:all.value.reduce((n,r)=>n+r.hits,0),unit:'条'},{label:'平均响应',value:1.2,unit:'秒'}])
const agent=(id:string)=>agents.find(a=>a.id===id) || agents[0]
</script>
<template><div class="page"><AppBreadcrumb/><PageHeader title="服务记录" subtitle="智能体与居民的每一次问答都会留痕，包含引用资料数量，便于服务质量追溯。"/><div class="kb-stats"><div v-for="stat in stats" :key="stat.label" class="mini-stat"><div class="ms-label">{{ stat.label }}</div><div class="ms-val">{{ stat.value }}<small>{{ stat.unit }}</small></div></div></div><div class="card"><div class="card-head"><b>问答记录 <span class="badge">{{ all.length }}</span></b><span class="sub">按时间倒序</span></div><div class="table-wrap"><table class="table"><thead><tr><th>服务时间</th><th>智能体</th><th>居民问题</th><th>引用资料</th><th>状态</th><th style="text-align:right">操作</th></tr></thead><tbody><tr v-for="(r,i) in all" :key="i"><td class="muted num">{{ r.time }}</td><td><span class="badge" :style="{'--tint':agent(r.agentId).tint}">{{ agent(r.agentId).name }}</span></td><td class="q-cell" :title="r.q">{{ r.q }}</td><td class="num">{{ r.hits }} 条</td><td><span class="badge" :class="{green:!r.demo}">{{ r.demo ? '示例记录' : r.status || '已回复' }}</span></td><td><div class="row-actions"><RouterLink class="link-btn" :to="`/agent/${r.agentId}`">查看对话</RouterLink></div></td></tr></tbody></table></div></div></div></template>
