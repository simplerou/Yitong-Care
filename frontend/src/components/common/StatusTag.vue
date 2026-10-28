<script setup lang="ts">
import { computed } from 'vue'
import { useDemoStore } from '../../stores/demo'
import type { KnowledgeDocument } from '../../types/models'
const props = defineProps<{ doc: KnowledgeDocument }>(), store = useDemoStore()
const status = computed(() => {
  if (props.doc.persisted) {
    const statuses: Record<string, string[]> = { vectorizing: ['blue', '向量化中…'], parsing: ['amber', '解析中…'], parsed: ['amber', '待处理'], failed: ['red', '解析失败'], chunked: ['blue', '已切块'], vectorized: ['green', '已入库'] }
    return statuses[props.doc.status] || ['', props.doc.status]
  }
  const chunks = store.state.chunks.filter(c => c.docId === props.doc.id)
  return props.doc.parsing ? ['amber', '解析中…'] : chunks.length && chunks.every(c => c.vectorized) ? ['green', '已入库'] : chunks.length ? ['blue', '已切块'] : ['amber', '待处理']
})
</script>
<template><span class="badge" :class="status[0]">{{ status[1] }}</span></template>
