<script setup lang="ts">
import type { DrugMention } from '../../api/medication'
const props = defineProps<{ drugs: DrugMention[]; unknown?: string[] }>()
const frequencyLabels: Record<string, string> = {
  once_daily: '每天一次', twice_daily: '每天两次', three_daily: '每天三次',
  four_daily: '每天四次', weekly: '每周一次', as_needed: '按需服用', unknown: '',
}
</script>
<template>
  <section v-if="props.drugs.length || (props.unknown && props.unknown.length)" class="drugs" aria-label="识别到的药物">
    <header><b>识别到的药物</b><span class="badge blue">{{ props.drugs.length }} 种</span></header>
    <ul>
      <li v-for="drug in props.drugs" :key="drug.canonical">
        <div class="drug-row">
          <span class="drug-name">{{ drug.name }}</span>
          <span class="drug-class">{{ drug.class_label }}</span>
          <span v-if="frequencyLabels[drug.user_frequency]" class="badge blue">{{ frequencyLabels[drug.user_frequency] }}</span>
        </div>
        <p v-if="drug.indication" class="drug-line">{{ drug.indication }}</p>
        <p v-if="drug.timing_hint" class="drug-line">常见服用时间：{{ drug.timing_hint }}</p>
      </li>
    </ul>
    <p v-if="props.unknown && props.unknown.length" class="drug-unknown">未收录：{{ props.unknown.join('、') }}（暂无法核对相互作用，请让药师确认）</p>
    <p class="drug-note">以上为常见信息，不是处方；具体用法以说明书和医嘱为准。</p>
  </section>
</template>
<style scoped>
.drugs { border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:13px; }
.drugs header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.drugs ul { list-style:none; margin:8px 0 0; padding:0; display:grid; gap:8px; }
.drugs li { border-top:1px dashed var(--line); padding-top:8px; }
.drugs li:first-child { border-top:0; padding-top:0; }
.drug-row { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }
.drug-name { font-weight:600; }
.drug-class { color:var(--muted); }
.drug-line { margin:4px 0 0; color:var(--muted); font-size:12px; line-height:1.6; }
.drug-unknown { margin:8px 0 0; color:#94540b; }
.drug-note { margin:6px 0 0; color:var(--muted); font-size:12px; }
</style>
