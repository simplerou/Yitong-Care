<script setup lang="ts">
import type { PortionReference } from '../../api/diet'
const props = defineProps<{ reference: PortionReference }>()
</script>
<template>
  <section class="portion" aria-label="每日膳食构成参考">
    <header><b>每日膳食构成参考</b><span class="badge blue">{{ props.reference.table_version }}</span></header>
    <ul>
      <li v-for="item in props.reference.items" :key="item.name">
        <span class="portion-name">{{ item.name }}</span>
        <span class="portion-range">{{ item.range_text }}</span>
        <span v-if="item.note" class="portion-note">{{ item.note }}</span>
      </li>
    </ul>
    <p class="portion-disclaimer">{{ props.reference.disclaimer }}</p>
  </section>
</template>
<style scoped>
.portion { border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:13px; }
.portion header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.portion ul { list-style:none; margin:8px 0 0; padding:0; display:grid; gap:6px; }
.portion li { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }
.portion-name { min-width:96px; color:var(--muted); }
.portion-range { font-weight:600; }
.portion-note { color:var(--muted); font-size:12px; }
.portion-disclaimer { margin:8px 0 0; color:var(--muted); font-size:12px; line-height:1.7; }
</style>
