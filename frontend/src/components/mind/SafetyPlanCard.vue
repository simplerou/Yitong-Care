<script setup lang="ts">
const props = defineProps<{ steps: string[] }>()
</script>
<template>
  <section v-if="props.steps.length" class="plan" aria-label="安全计划">
    <header><b>这几天的安全计划</b><span class="badge blue">{{ props.steps.length }} 步</span></header>
    <ol>
      <li v-for="(step, index) in props.steps" :key="index">{{ step }}</li>
    </ol>
    <p class="note">计划可以写在纸上贴在显眼处，也可以和家人一起过一遍。</p>
  </section>
</template>
<style scoped>
.plan { border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:13px; }
.plan header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.plan ol { margin:8px 0 0; padding-left:20px; display:grid; gap:6px; line-height:1.7; }
.note { margin:8px 0 0; color:var(--muted); font-size:12px; }
</style>
