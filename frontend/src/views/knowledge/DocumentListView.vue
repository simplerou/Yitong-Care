<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useKnowledgeStore } from '../../stores/knowledge'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import UploadDropzone from '../../components/knowledge/UploadDropzone.vue'
import DocumentTable from '../../components/knowledge/DocumentTable.vue'
const store = useKnowledgeStore(), draft = ref(store.query), kbId = ref('general'), source = ref('本地上传')
const upload = ref<InstanceType<typeof UploadDropzone>>()
let timer: ReturnType<typeof setInterval>
function search() { store.page = 1; store.query = draft.value; void store.load() }
function page(direction: number) { store.page += direction; void store.load() }
watch(() => store.query, value => { draft.value = value })
onMounted(() => {
  void store.load(); void store.loadBases()
  timer = setInterval(() => {
    if (!store.loading && store.documents.some(d => d.parsing)) void store.load()
  }, 1500)
})
onBeforeUnmount(() => clearInterval(timer))
</script>
<template>
  <div class="page">
    <AppBreadcrumb />
    <PageHeader title="知识库管理" subtitle="上传养老领域文档，作为智能体问答与向量检索的知识来源。">
      <button class="btn" :disabled="store.uploading" @click="store.loadDemo(kbId)"><AppIcon name="sparkles" :size="14" /> 载入示例文档</button>
      <button class="btn primary" :disabled="store.uploading" @click="upload?.pick()"><AppIcon name="upload" :size="14" /> 上传文档</button>
    </PageHeader>
    <div v-if="store.error" class="knowledge-error" role="alert"><span>{{ store.error }}</span><button class="btn sm" @click="store.load(); store.loadBases()">重新加载</button></div>
    <div class="kb-stats">
      <div v-for="stat in [{ label:'知识文档', value:store.stats.documents, unit:'份' }, { label:'文本块', value:store.stats.chunks, unit:'段' }, { label:'已入库向量', value:store.stats.vectors, unit:'条' }, { label:'待处理文档', value:store.stats.pending, unit:'份' }]" :key="stat.label" class="mini-stat">
        <div class="ms-label">{{ stat.label }}</div><div class="ms-val">{{ stat.value }}<small>{{ stat.unit }}</small></div>
      </div>
    </div>
    <div class="upload-metadata">
      <label>存入知识库<select v-model="kbId" class="select" :disabled="store.uploading"><option v-if="!store.bases.length" value="general">通用知识库</option><option v-for="base in store.bases" :key="base.id" :value="base.id">{{ base.name }}</option></select></label>
      <label>资料来源<input v-model="source" class="input" maxlength="512" :disabled="store.uploading" placeholder="例如：社区服务中心"></label>
    </div>
    <UploadDropzone ref="upload" :kb-id="kbId" :source="source" />
    <div class="card" :aria-busy="store.loading">
      <div class="card-head"><b>知识文档 <span class="badge">{{ store.stats.documents }}</span></b>
        <form style="display:flex;gap:8px;align-items:center" @submit.prevent="search">
          <input id="kbSearch" v-model="draft" class="input" aria-label="搜索文档名称" maxlength="100" placeholder="搜索文档名称，回车筛选" style="width:230px;height:32px;font-size:12.5px">
          <button class="btn sm" type="submit" :disabled="store.loading">搜索</button>
        </form>
      </div>
      <div v-if="store.loading && !store.documents.length" class="knowledge-loading" role="status"><span class="spinner"></span> 正在加载文档…</div>
      <DocumentTable v-else-if="store.documents.length || store.query" :documents="store.documents" />
      <EmptyState v-else-if="!store.error" icon="book" title="知识库还是空的" description="上传第一份文档，开始构建智能体的知识来源" />
      <div v-if="store.total > store.pageSize" class="document-pagination">
        <span>共 {{ store.total }} 份 · 第 {{ store.page }} / {{ Math.ceil(store.total / store.pageSize) }} 页</span>
        <button class="btn sm" :disabled="store.page <= 1 || store.loading" @click="page(-1)">上一页</button>
        <button class="btn sm" :disabled="store.page * store.pageSize >= store.total || store.loading" @click="page(1)">下一页</button>
      </div>
    </div>
    <p class="hint" style="margin-top:12px">文档、切块、向量入库与检索已接入真实后端；Agent 问答仍为演示。</p>
  </div>
</template>
