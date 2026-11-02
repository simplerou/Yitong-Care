<script setup lang="ts">
import type { ScreeningResult, RiskSignal } from '../../api/mind'
const props = defineProps<{ signals: RiskSignal[]; screening?: ScreeningResult | null; riskLevel?: string | null }>()
const levelLabels: Record<string, string> = { low: '较低', medium: '需要关注', high: '较高', critical: '需要立即支持' }
const protective = (signals: RiskSignal[]) => signals.filter(signal => signal.kind === 'protective').map(signal => signal.label)
const triggers = (signals: RiskSignal[]) => signals.filter(signal => signal.kind === 'trigger').map(signal => signal.label)
</script>
<template>
  <section v-if="props.signals.length || props.screening" class="emotion" aria-label="本次对话中的情绪信号">
    <header>
      <b>我听到的这些</b>
      <span v-if="props.riskLevel" class="badge blue">风险提示：{{ levelLabels[props.riskLevel] || props.riskLevel }}</span>
    </header>
    <p v-if="triggers(props.signals).length" class="line">近期变化：{{ triggers(props.signals).join('、') }}</p>
    <p v-if="protective(props.signals).length" class="line">身边的支撑：{{ protective(props.signals).join('、') }}</p>
    <p v-if="props.screening?.positive" class="line">近两周情绪低落伴兴趣减退，这不等于诊断，但值得找专业人员评估一次。</p>
    <p class="note">这些是程序根据你的原话整理的关键词，不是诊断；如果你觉得不准，可以告诉我。</p>
  </section>
</template>
<style scoped>
.emotion { border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:13px; }
.emotion header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.line { margin:8px 0 0; color:var(--ink-2); line-height:1.7; }
.note { margin:8px 0 0; color:var(--muted); font-size:12px; }
</style>
