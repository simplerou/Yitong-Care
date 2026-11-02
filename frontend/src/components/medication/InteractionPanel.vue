<script setup lang="ts">
import type { InteractionFinding } from '../../api/medication'
const props = defineProps<{ findings: InteractionFinding[] }>()
const labels: Record<string, string> = { high: '需尽快核对', moderate: '需要关注', note: '用药提示' }
const tone = (severity: string) => severity === 'high' ? 'high' : severity === 'moderate' ? 'moderate' : 'note'
</script>
<template>
  <section v-if="props.findings.length" class="interactions" aria-label="相互作用与用药风险">
    <header><b>相互作用与用药风险</b><span class="badge blue">{{ props.findings.length }} 项</span></header>
    <ul>
      <li v-for="finding in props.findings" :key="finding.id" :class="tone(finding.severity)">
        <div class="row">
          <span class="severity">{{ labels[finding.severity] }}</span>
          <span class="title">{{ finding.title }}</span>
          <span class="names">{{ finding.drugs.join('、') }}</span>
        </div>
        <p class="detail">{{ finding.detail }}</p>
        <p class="action">{{ finding.action }}</p>
      </li>
    </ul>
    <p class="note">是否需要调整用药由医生或药师判断，请勿自行停药、加量或减量。</p>
  </section>
</template>
<style scoped>
.interactions { border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:13px; }
.interactions header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.interactions ul { list-style:none; margin:8px 0 0; padding:0; display:grid; gap:10px; }
.interactions li { border-top:1px dashed var(--line); padding-top:8px; }
.interactions li:first-child { border-top:0; padding-top:0; }
.row { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }
.severity { font-weight:600; }
.title { font-weight:600; }
.names { color:var(--muted); }
.detail { margin:4px 0 0; color:var(--ink-2); line-height:1.7; }
.action { margin:4px 0 0; color:var(--brand); line-height:1.7; }
.note { margin:8px 0 0; color:var(--muted); font-size:12px; }
.high .severity { color:#a3231b; }
.moderate .severity { color:#94540b; }
.note .severity { color:var(--muted); }
</style>
