<script setup lang="ts">
import type { NutritionFinding } from '../../api/diet'
const props = defineProps<{ findings: NutritionFinding[]; risks?: string[] }>()
const labels: Record<string, string> = { high: '需尽快核对', moderate: '需要关注', note: '饮食提示' }
const tone = (severity: string) => severity === 'high' ? 'high' : severity === 'moderate' ? 'moderate' : 'note'
</script>
<template>
  <section v-if="props.findings.length || (props.risks && props.risks.length)" class="nutrition" aria-label="需要留意的饮食问题">
    <header><b>需要留意的饮食问题</b><span class="badge blue">{{ props.findings.length }} 项</span></header>
    <p v-if="props.risks && props.risks.length" class="risks">膳食模式提示：{{ props.risks.join('、') }}。</p>
    <ul>
      <li v-for="finding in props.findings" :key="finding.id" :class="tone(finding.severity)">
        <div class="row">
          <span class="severity">{{ labels[finding.severity] }}</span>
          <span class="title">{{ finding.title }}</span>
          <span v-if="finding.foods.length" class="names">{{ finding.foods.join('、') }}</span>
        </div>
        <p class="detail">{{ finding.detail }}</p>
        <p class="action">{{ finding.action }}</p>
      </li>
    </ul>
    <p class="note">限制量与禁忌由医生或营养师确定，请勿据此自行严格限制或大量补充。</p>
  </section>
</template>
<style scoped>
.nutrition { border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:13px; }
.nutrition header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.risks { margin:8px 0 0; color:#94540b; }
.nutrition ul { list-style:none; margin:8px 0 0; padding:0; display:grid; gap:10px; }
.nutrition li { border-top:1px dashed var(--line); padding-top:8px; }
.nutrition li:first-child { border-top:0; padding-top:0; }
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
