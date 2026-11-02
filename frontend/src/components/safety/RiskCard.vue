<script setup lang="ts">
import type { RiskFactor, RiskLevel } from '../../api/safety'
const props = defineProps<{ factors: RiskFactor[]; level: RiskLevel | null }>()
const levelLabels: Record<string, string> = { low: '较低', medium: '中等', high: '较高' }
const tone = (level: string | null) => level === 'high' ? 'high' : level === 'medium' ? 'medium' : 'low'
</script>
<template>
  <section v-if="props.factors.length || props.level" class="risk" :class="tone(props.level)">
    <header>
      <b>跌倒风险因素</b>
      <span v-if="props.level" class="badge" :class="tone(props.level) === 'high' ? 'red' : 'blue'">综合评估：{{ levelLabels[props.level] }}</span>
    </header>
    <ul>
      <li v-for="factor in props.factors" :key="factor.id">
        <span class="factor-label">{{ factor.label }}</span>
        <span class="factor-action">{{ factor.action }}</span>
      </li>
    </ul>
    <p v-if="!props.factors.length" class="risk-empty">暂未发现明确的跌倒风险因素，可按居家清单逐项自查。</p>
  </section>
</template>
<style scoped>
.risk { border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:13px; }
.risk header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.risk ul { list-style:none; margin:8px 0 0; padding:0; display:grid; gap:6px; }
.risk li { display:flex; gap:8px; flex-wrap:wrap; align-items:baseline; }
.factor-label { font-weight:600; min-width:120px; }
.factor-action { color:var(--muted); flex:1 1 220px; line-height:1.6; }
.risk-empty { margin:8px 0 0; color:var(--muted); }
.risk.high { border-color:#f0b4ae; }
.risk.medium { border-color:#f5cf9a; }
</style>
