<script setup lang="ts">
defineProps<{ icon: string; title: string; description: string }>()
</script>
<template><div class="empty"><div class="empty-ico"><AppIcon :name="icon" :size="26"/></div><b>{{ title }}</b><p>{{ description }}</p><slot/></div></template>
