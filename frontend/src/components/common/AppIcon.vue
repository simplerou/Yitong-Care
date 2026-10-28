<script setup lang="ts">
import { ICONS } from '../../demo/data'
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })
const paths = ICONS as Record<string, string[]>
</script>
<template><svg class="ico" :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path v-for="(d, i) in paths[name] || []" :key="i" :d="d" /></svg></template>
