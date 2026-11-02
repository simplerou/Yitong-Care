<script setup lang="ts">
import type { VitalsAssessment } from '../../api/health'
const props = defineProps<{ assessment: VitalsAssessment }>()
const metricLabels: Record<string, string> = {
  blood_pressure: '血压', heart_rate: '心率', fasting_glucose: '空腹血糖',
  postprandial_glucose: '餐后血糖', random_glucose: '血糖', spo2: '血氧', temperature: '体温', weight: '体重',
}
const missingLabels: Record<string, string> = {
  measurement_context: '测量情境（家庭/诊室）', measurement_time: '测量时间', fasting_status: '空腹或餐后',
  diastolic_value: '舒张压', symptoms: '伴随症状', age: '年龄', conditions: '基础疾病', explicit_value: '数值待确认',
}
const flagLabels: Record<string, string> = { implausible: '数值异常，未参与判读', unit_converted: '已换算单位' }
const label = (metric: string) => metricLabels[metric] || '指标'
const missing = (keys: string[]) => keys.map(key => missingLabels[key] || key)
const flags = (list: string[]) => list.map(flag => flagLabels[flag] || flag)
</script>
<template>
  <section class="vitals" aria-label="本次指标判读">
    <header><b>指标判读</b><span class="badge blue">判读表 {{ props.assessment.table_version }}</span></header>
    <ul>
      <li v-for="(reading, index) in props.assessment.readings" :key="index" :class="{ implausible: reading.category_code === 'unverified' }">
        <div class="vitals-row">
          <span class="vitals-metric">{{ label(reading.metric) }}</span>
          <span class="vitals-display">{{ reading.display }}</span>
          <span class="vitals-category">{{ reading.category }}</span>
        </div>
        <p class="vitals-basis">{{ reading.reference_basis }}</p>
        <p v-if="reading.flags.length" class="vitals-flag">{{ flags(reading.flags).join(' · ') }}</p>
      </li>
    </ul>
    <p v-if="props.assessment.missing.length" class="vitals-missing">还需补充：{{ missing(props.assessment.missing).join('、') }}</p>
    <p class="vitals-note">分级由程序按固定判读表计算，不由模型生成；个体目标仍需医生确定。</p>
  </section>
</template>
<style scoped>
.vitals { border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:13px; }
.vitals header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.vitals ul { list-style:none; margin:8px 0 0; padding:0; display:grid; gap:8px; }
.vitals li { border-top:1px dashed var(--line); padding-top:8px; }
.vitals li:first-child { border-top:0; padding-top:0; }
.vitals-row { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }
.vitals-metric { color:var(--muted); min-width:64px; }
.vitals-display { font-weight:600; }
.vitals-category { color:var(--brand); }
.vitals-basis { margin:4px 0 0; color:var(--muted); font-size:12px; line-height:1.6; }
.vitals-flag { margin:2px 0 0; color:#94540b; font-size:12px; }
.vitals-missing { margin:8px 0 0; color:#94540b; }
.vitals-note { margin:6px 0 0; color:var(--muted); font-size:12px; }
.implausible .vitals-category { color:#94540b; }
</style>
