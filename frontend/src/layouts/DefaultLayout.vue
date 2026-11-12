<script setup lang="ts">
import { nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from '../components/layout/AppHeader.vue'
import AppSidebar from '../components/layout/AppSidebar.vue'
const route = useRoute()
watch(() => route.fullPath, async () => { await nextTick(); document.getElementById('main')?.scrollTo({ top: 0 }) })
</script>
<template><div class="app"><AppHeader/><div class="shell"><AppSidebar/><main id="main" class="main" tabindex="-1"><RouterView/></main></div></div></template>
