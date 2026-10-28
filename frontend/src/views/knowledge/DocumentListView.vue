<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDemoStore } from '../../stores/demo'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import UploadDropzone from '../../components/knowledge/UploadDropzone.vue'
import DocumentTable from '../../components/knowledge/DocumentTable.vue'
const store = useDemoStore(), search = ref(''), draft = ref(''), upload = ref<InstanceType<typeof UploadDropzone>>()
const documents = computed(()=>store.state.docs.filter(d=>d.name.includes(search.value.trim())))
const pending = computed(()=>store.state.docs.filter(d=>d.status !== 'vectorized' || d.parsing).length)
</script>
<template><div class="page"><AppBreadcrumb/><PageHeader title="知识库管理" subtitle="上传养老领域文档，作为智能体问答与向量检索的知识来源。"><button class="btn" @click="store.loadDemo"><AppIcon name="sparkles" :size="14"/> 载入示例文档</button><button class="btn primary" @click="upload?.pick()"><AppIcon name="upload" :size="14"/> 上传文档</button></PageHeader><div class="kb-stats"><div v-for="stat in [{label:'知识文档',value:store.state.docs.length,unit:'份'},{label:'文本块',value:store.state.chunks.length,unit:'段'},{label:'已入库向量',value:store.vectorCount,unit:'条'},{label:'待处理文档',value:pending,unit:'份'}]" :key="stat.label" class="mini-stat"><div class="ms-label">{{ stat.label }}</div><div class="ms-val">{{ stat.value }}<small>{{ stat.unit }}</small></div></div></div><UploadDropzone ref="upload"/><div class="card"><div class="card-head"><b>知识文档 <span class="badge">{{ store.state.docs.length }}</span></b><div style="display:flex;gap:8px;align-items:center"><input id="kbSearch" v-model="draft" class="input" aria-label="搜索文档名称" placeholder="搜索文档名称，回车筛选" style="width:230px;height:32px;font-size:12.5px" @keydown.enter="search=draft"></div></div><DocumentTable v-if="store.state.docs.length" :documents="documents"/><EmptyState v-else icon="book" title="知识库还是空的" description="上传第一份文档，开始构建智能体的知识来源"/></div></div></template>
