<script setup lang="ts">
defineProps<{ title: string; subtitle: string }>()
</script>
<template><div class="page-head"><div><h1 class="page-title">{{ title }}</h1><p class="page-sub">{{ subtitle }}</p></div><div v-if="$slots.default" class="page-actions"><slot/></div></div></template>
