<script setup lang="ts">
import { useDemoStore } from '../../stores/demo'
const store = useDemoStore()
</script>
<template><div id="toastRoot" class="toast-root" aria-live="polite"><div v-if="store.toast" class="toast" :class="store.toast.type === 'success' ? '' : store.toast.type"><span class="toast-ico"><AppIcon :name="store.toast.type === 'error' ? 'x' : store.toast.type === 'warn' ? 'info' : 'check'" :size="10"/></span>{{ store.toast.text }}</div></div></template>
