<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useKnowledgeStore } from '../../stores/knowledge'
import { useOverlay } from '../../composables/useOverlay'
import StatusTag from '../common/StatusTag.vue'
import type { KnowledgeDocument } from '../../types/models'
defineProps<{ documents: KnowledgeDocument[] }>()
const store = useKnowledgeStore(), router = useRouter(), ui = useOverlay()
function go(id: string,vector=false) { store.selectedDocId = id; void router.push(vector?'/vector':'/chunk') }
const canRetry = (d: KnowledgeDocument) => d.status === 'failed' || (d.parsing && !!d.updatedAt && Date.now() - Date.parse(d.updatedAt) >= 10 * 60 * 1000)
</script>
<template>
  <div class="table-wrap"><table class="table">
    <thead><tr><th>文档名称</th><th>类型</th><th>大小</th><th>已切块</th><th>状态</th><th>上传时间</th><th style="text-align:right">操作</th></tr></thead>
    <tbody>
      <tr v-for="d in documents" :key="d.id">
        <td><div class="name"><span class="doc-ico"><AppIcon name="doc" :size="15" /></span>
          <div><div>{{ d.name }}</div><div class="meta-cell">{{ d.source }}</div>
            <div v-if="d.errorMessage" class="document-error">{{ d.errorMessage }}</div>
          </div>
        </div></td>
        <td><span class="badge">{{ d.type }}</span></td><td class="muted num">{{ d.size }}</td>
        <td class="num">{{ d.chunkCount ? `${d.chunkCount} 段` : '—' }}</td>
        <td><StatusTag :doc="d" /></td><td class="muted num">{{ d.uploadAt }}</td>
        <td><div class="row-actions">
          <button class="link-btn" :disabled="store.detailBusy" @click="store.detail(d.id)">查看</button>
          <button v-if="canRetry(d)" class="link-btn" :disabled="!!store.busyId" @click="store.retry(d.id)">重试</button>
          <button v-else class="link-btn" :disabled="d.parsing || d.status==='vectorizing'" @click="go(d.id)">切块</button>
          <button class="link-btn" :disabled="!d.chunkCount || d.parsing" title="向量入库" @click="go(d.id,true)">入库</button>
          <button class="link-btn danger" :disabled="d.parsing || d.status==='vectorizing' || !!store.busyId"
            @click="ui.confirm('删除文档', `将删除「${d.name}」的原文件、正文和文本块，并使相关向量索引失效，且不可恢复。`, () => { void store.remove(d.id) }, '确认删除')">删除</button>
        </div></td>
      </tr>
      <tr v-if="!documents.length"><td colspan="7" style="text-align:center;padding:30px">没有匹配的文档，请尝试其他名称。</td></tr>
    </tbody>
  </table></div>
</template>
