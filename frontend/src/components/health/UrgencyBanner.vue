<script setup lang="ts">
import { computed } from 'vue'
import type { Urgency } from '../../api/health'
const props = defineProps<{ urgency: Urgency | null; redFlags?: string[]; status?: string; requiredAction?: string | null }>()
const tone = computed(() => props.urgency === 'L1' ? 'critical' : props.urgency === 'L2' ? 'urgent' : props.urgency === 'L3' ? 'watch' : 'routine')
const title = computed(() => {
  if (props.status === 'emergency' || props.urgency === 'L1') return '需要立即处理'
  if (props.urgency === 'L2') return '建议 24 小时内就医'
  if (props.urgency === 'L3') return '建议近期门诊复查'
  return '本次为自我照护建议'
})
const detail = computed(() => {
  if (props.status === 'emergency' || props.urgency === 'L1') return '请立即拨打 120 或前往急诊，不要自行服药或等待观察。'
  if (props.urgency === 'L2') return '请尽快联系家庭医生或前往门诊，并带上测量记录与正在服用的药物。'
  if (props.urgency === 'L3') return '把这段时间的测量记录带给医生，按医嘱复诊。'
  return ''
})
</script>
<template>
  <section class="urgency" :class="tone" :role="tone === 'critical' ? 'alert' : 'status'">
    <div class="urgency-head">
      <span class="urgency-dot" aria-hidden="true"></span>
      <b>{{ title }}</b>
      <a v-if="tone === 'critical'" class="urgency-call" href="tel:120">拨打 120</a>
    </div>
    <p v-if="detail">{{ detail }}</p>
    <p v-if="redFlags?.length" class="urgency-flags">本次识别到：{{ redFlags.join('、') }}（由程序规则判断，不替代医生评估）</p>
  </section>
</template>
<style scoped>
.urgency { border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:13px; line-height:1.7; }
.urgency p { margin:4px 0 0; }
.urgency-head { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.urgency-dot { width:9px; height:9px; border-radius:50%; background:currentColor; flex:0 0 auto; }
.urgency-flags { color:var(--muted); font-size:12px; }
.urgency-call { margin-left:auto; min-height:36px; display:inline-flex; align-items:center; padding:0 12px; border-radius:8px; background:#b42318; color:#fff; font-weight:600; text-decoration:none; }
.critical { border-color:#f0b4ae; background:#fff3f2; color:#a3231b; }
.urgent { border-color:#f5cf9a; background:#fff8ed; color:#94540b; }
.watch { border-color:#bcd4f7; background:#f2f7ff; color:#1b4f9c; }
.routine { border-color:var(--line); background:var(--surface,#fff); color:var(--ink-2); }
</style>
