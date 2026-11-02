<script setup lang="ts">
const props = defineProps<{ notice?: string | null }>()
</script>
<template>
  <section v-if="props.notice" class="crisis" role="alert">
    <header><b>现在最重要的不是"想开点"</b><span class="badge red">需要立即获得支持</span></header>
    <p class="notice">{{ props.notice }}</p>
    <div class="actions">
      <a class="crisis-call" href="tel:120">拨打 120</a>
      <a class="crisis-line" href="tel:12356">心理援助热线 12356</a>
    </div>
  </section>
</template>
<style scoped>
.crisis { border:1px solid #f0b4ae; background:#fff5f4; border-radius:12px; padding:12px 16px; margin:10px 0; color:#7a1c14; }
.crisis header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.notice { margin:8px 0 0; white-space:pre-wrap; line-height:1.9; }
.actions { display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }
.actions a { display:inline-flex; align-items:center; min-height:40px; padding:0 14px; border-radius:8px; font-weight:600; text-decoration:none; }
.crisis-call { background:#b42318; color:#fff; }
.crisis-line { background:#fff; color:#b42318; border:1px solid #f0b4ae; }
</style>
