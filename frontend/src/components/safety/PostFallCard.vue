<script setup lang="ts">
import type { PostFallFinding } from '../../api/safety'
const props = defineProps<{ findings: PostFallFinding[]; advice?: string | null }>()
const labels: Record<string, string> = { high: '立即处理', moderate: '尽快就医', note: '观察' }
const tone = (severity: string) => severity === 'high' ? 'high' : severity === 'moderate' ? 'medium' : 'note'
</script>
<template>
  <section v-if="props.findings.length" class="postfall" aria-label="跌倒后需要判断的情况">
    <header><b>跌倒后需要判断的情况</b><span class="badge blue">{{ props.findings.length }} 项</span></header>
    <ul>
      <li v-for="item in props.findings" :key="item.id" :class="tone(item.severity)">
        <div class="row"><span class="severity">{{ labels[item.severity] }}</span><span class="title">{{ item.title }}</span></div>
        <p class="detail">{{ item.detail }}</p>
        <p class="action">{{ item.action }}</p>
      </li>
    </ul>
    <p v-if="props.advice" class="advice">{{ props.advice }}</p>
  </section>
</template>
<style scoped>
.postfall { border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:13px; }
.postfall header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.postfall ul { list-style:none; margin:8px 0 0; padding:0; display:grid; gap:10px; }
.postfall li { border-top:1px dashed var(--line); padding-top:8px; }
.postfall li:first-child { border-top:0; padding-top:0; }
.row { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }
.severity { font-weight:600; }
.title { font-weight:600; }
.detail { margin:4px 0 0; color:var(--ink-2); line-height:1.7; }
.action { margin:4px 0 0; color:var(--brand); line-height:1.7; }
.advice { margin:10px 0 0; padding-top:8px; border-top:1px solid var(--line); color:var(--ink); line-height:1.9; }
.high .severity { color:#a3231b; }
.medium .severity { color:#94540b; }
</style>
