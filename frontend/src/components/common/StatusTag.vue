<script setup lang="ts">
import { computed } from 'vue'
import { useDemoStore } from '../../stores/demo'
import type { KnowledgeDocument } from '../../types/models'
const props = defineProps<{ doc: KnowledgeDocument }>(), store = useDemoStore()
const status = computed(() => { const chunks = store.state.chunks.filter(c => c.docId === props.doc.id); return props.doc.parsing ? ['amber', '解析中…'] : chunks.length && chunks.every(c => c.vectorized) ? ['green', '已入库'] : chunks.length ? ['blue', '已切块'] : ['amber', '待处理'] })
</script>
<template><span class="badge" :class="status[0]">{{ status[1] }}</span></template>
