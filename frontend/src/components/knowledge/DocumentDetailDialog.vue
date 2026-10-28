<script setup lang="ts">
import type { Chunk, KnowledgeDocument } from '../../types/models'
defineProps<{ doc: KnowledgeDocument; chunks: Chunk[] }>()
const emit = defineEmits<{ openChunk: [chunk: Chunk] }>()
</script>
<template>
  <div class="modal-body">
    <div class="doc-detail-grid">
      <div v-for="[label,value] in [['文件类型', doc.type], ['文件大小', doc.size], ['上传时间', doc.uploadAt], ['切块数量', `${chunks.length} 段`], ['已入库', `${doc.vectorCount || 0} 条`], ['来源', doc.source]]" :key="label" class="kv"><span>{{ label }}</span><b>{{ value }}</b></div>
    </div>
    <div v-if="doc.errorMessage" class="knowledge-error" role="alert">{{ doc.errorMessage }}</div>
    <template v-if="doc.text">
      <div class="card-head" style="padding:0 0 10px;border:0"><b>解析正文</b><span class="sub">{{ doc.text.length }} 字符</span></div>
      <div class="original-text document-body">{{ doc.text }}</div>
    </template>
    <div v-else-if="doc.parsing" class="knowledge-loading" role="status">正在解析正文，请稍后重新查看。</div>
    <div class="card-head" style="padding:14px 0 10px;border:0"><b>已保存文本块</b><span class="sub">共 {{ chunks.length }} 段，点击查看原文</span></div>
    <div class="document-chunks">
      <button v-for="c in chunks" :key="c.id" class="chunk-row" @click="emit('openChunk', c)">
        <span class="chunk-no">{{ c.index }}</span><div class="chunk-content"><div class="chunk-text">{{ c.text }}</div>
          <div class="chunk-meta"><span>{{ c.chars }} 字</span><span>字符 {{ c.start }}–{{ c.start + c.chars }}</span><span>{{ c.vectorized ? '已向量化' : '未入库' }}</span></div>
        </div>
      </button>
      <div v-if="!chunks.length" class="hint" style="padding:24px;text-align:center">该文档尚未保存切块结果。</div>
    </div>
  </div>
</template>
