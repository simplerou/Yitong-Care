<script setup lang="ts">
import { nextTick, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from '../components/layout/AppHeader.vue'
import AppSidebar from '../components/layout/AppSidebar.vue'
import { useRetrievalStore } from '../stores/retrieval'
import { useKnowledgeStore } from '../stores/knowledge'
const knowledge = useKnowledgeStore(), retrieval = useRetrievalStore()
onMounted(() => { void knowledge.load(); void retrieval.loadLogs() })
const route = useRoute()
watch(() => route.fullPath, async () => { await nextTick(); document.getElementById('main')?.scrollTo({ top: 0 }) })
</script>
<template><div class="app"><AppHeader/><div class="shell"><AppSidebar/><main id="main" class="main" tabindex="-1"><RouterView/></main></div></div></template>
