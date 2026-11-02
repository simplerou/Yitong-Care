<script setup lang="ts">
import type { HazardFinding } from '../../api/safety'
const props = defineProps<{ hazards: HazardFinding[] }>()
const labels: Record<string, string> = { high: '优先处理', moderate: '建议改造', note: '可以优化' }
const tone = (severity: string) => severity === 'high' ? 'high' : severity === 'moderate' ? 'medium' : 'note'
</script>
<template>
  <section v-if="props.hazards.length" class="hazards" aria-label="本次提到的居家隐患">
    <header><b>本次提到的居家隐患</b><span class="badge blue">{{ props.hazards.length }} 处</span></header>
    <ul>
      <li v-for="hazard in props.hazards" :key="hazard.id" :class="tone(hazard.severity)">
        <div class="row">
          <span class="room">{{ hazard.room }}</span>
          <span class="severity">{{ labels[hazard.severity] }}</span>
          <span class="issue">{{ hazard.issue }}</span>
        </div>
        <p class="action">{{ hazard.action }}</p>
        <p v-if="hazard.reference" class="reference">{{ hazard.reference }}</p>
      </li>
    </ul>
    <p class="note">尺寸与安装位置为常见建议，具体由适老化改造人员或康复治疗师现场确定。</p>
  </section>
</template>
<style scoped>
.hazards { border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:13px; }
.hazards header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.hazards ul { list-style:none; margin:8px 0 0; padding:0; display:grid; gap:10px; }
.hazards li { border-top:1px dashed var(--line); padding-top:8px; }
.hazards li:first-child { border-top:0; padding-top:0; }
.row { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }
.room { font-weight:600; }
.severity { color:var(--brand); }
.issue { font-weight:600; }
.action { margin:4px 0 0; color:var(--ink-2); line-height:1.7; }
.reference { margin:4px 0 0; color:var(--muted); font-size:12px; }
.note { margin:8px 0 0; color:var(--muted); font-size:12px; }
.high .severity { color:#a3231b; }
.medium .severity { color:#94540b; }
</style>
