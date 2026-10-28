<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useKnowledgeStore, mapChunk } from '../../stores/knowledge'
import { useDemoStore } from '../../stores/demo'
import { chunksApi } from '../../api/chunks'
import type { Chunk } from '../../types/models'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import ChunkPreviewList from '../../components/knowledge/ChunkPreviewList.vue'
const knowledge = useKnowledgeStore(), toast = useDemoStore()
const size = ref(220), overlap = ref(30), chunks = ref<Chunk[]>([]), average = ref(0)
const loading = ref(false), saving = ref(false), error = ref(''), choicesLoading = ref(false)
const doc = computed(() => knowledge.choices.find(d => d.id === knowledge.selectedDocId))
const selectable = computed(() => knowledge.choices.filter(d => ['parsed', 'chunked', 'vectorized'].includes(d.status)))
const committed = computed(() => doc.value?.chunkCount || 0)
let timer: ReturnType<typeof setTimeout> | undefined
let controller: AbortController | undefined
let generation = 0, disposed = false
async function loadChoices() {
  choicesLoading.value = true
  try {
    await knowledge.loadChoices()
    if (disposed) return
    if (!selectable.value.some(d => d.id === knowledge.selectedDocId)) knowledge.selectedDocId = selectable.value[0]?.id || ''
    schedule()
  } catch (e) { error.value = e instanceof Error ? e.message : '文档加载失败。' }
  finally { choicesLoading.value = false }
}
function schedule() {
  clearTimeout(timer); controller?.abort(); generation++
  chunks.value = []; average.value = 0; error.value = ''
  if (!doc.value) { loading.value = false; return }
  if (overlap.value >= size.value) { error.value = '重叠长度必须小于切块大小。'; loading.value = false; return }
  loading.value = true
  const current = generation, id = doc.value.id, parameters = { size: size.value, overlap: overlap.value }
  timer = setTimeout(async () => {
    const requestController = new AbortController(); controller = requestController
    try {
      const result = await chunksApi.preview(id, parameters, requestController.signal)
      if (current !== generation || disposed) return
      chunks.value = result.chunks.map(mapChunk); average.value = result.average_chars
    } catch (e) {
      if (current === generation && !disposed && !requestController.signal.aborted) error.value = e instanceof Error ? e.message : '预览失败。'
    } finally { if (current === generation && !disposed) loading.value = false }
  }, 250)
}
async function save() {
  if (!doc.value || saving.value || loading.value || !chunks.value.length) return
  saving.value = true
  try {
    const result = await chunksApi.save(doc.value.id, { size: size.value, overlap: overlap.value })
    chunks.value = result.chunks.map(mapChunk)
    doc.value.chunkCount = result.count
    doc.value.vectorCount = 0
    doc.value.status = 'chunked'
    toast.notify(`已保存 ${result.count} 个文本块，原有向量已失效。`)
    // 保存已经成功，刷新失败不能把用户已提交的写入误报为失败。
    const refreshed = await Promise.allSettled([knowledge.load(), knowledge.loadChoices()])
    if (refreshed.some(result => result.status === 'rejected')) error.value = '切块已保存，文档列表刷新失败，请重新加载。'
  } catch (e) { toast.notify(e instanceof Error ? e.message : '保存失败。', 'error') }
  finally { saving.value = false }
}
watch([() => knowledge.selectedDocId, size, overlap], schedule)
onMounted(() => { void loadChoices() })
onBeforeUnmount(() => { disposed = true; generation++; clearTimeout(timer); controller?.abort() })
</script>
<template>
  <div class="page"><AppBreadcrumb />
    <PageHeader title="文本切块" subtitle="把长文档切成语义完整的小段，是向量化与召回质量的关键一步。">
      <span class="badge" :class="committed ? 'green' : 'amber'">{{ committed ? `当前已保存 ${committed} 段` : '尚未保存切块结果' }}</span>
    </PageHeader>
    <div v-if="error" class="knowledge-error" role="alert"><span>{{ error }}</span><button class="btn sm" @click="loadChoices">重试</button></div>
    <div v-if="choicesLoading" class="card knowledge-loading" role="status">正在加载文档…</div>
    <div v-else-if="!selectable.length && !error" class="card"><EmptyState icon="doc" title="还没有可切块的文档" description="请先上传文档，并等待正文解析完成。"><RouterLink class="btn primary" to="/kb">去上传文档</RouterLink></EmptyState></div>
    <div v-else class="split-2">
      <div class="card cfg-card">
        <div class="field"><label for="chunkDoc">选择文档</label><select id="chunkDoc" v-model="knowledge.selectedDocId" class="select" :disabled="saving"><option v-for="d in selectable" :key="d.id" :value="d.id">{{ d.name }}</option></select></div>
        <div class="field"><label for="sizeRange">切块大小 <b><span id="sizeVal">{{ size }}</span> 字符</b></label><input id="sizeRange" v-model.number="size" type="range" min="100" max="500" step="10" :disabled="saving"><div class="hint">建议 200–300 字，兼顾语义完整与检索精度。</div></div>
        <div class="field"><label for="ovRange">重叠长度 <b><span id="ovVal">{{ overlap }}</span> 字符</b></label><input id="ovRange" v-model.number="overlap" type="range" min="0" max="100" step="5" :disabled="saving"><div class="hint">按完整句子保留重叠，实际重叠字数可小于设定值。</div></div>
        <div class="field"><label>快捷预设</label><div class="presets"><button v-for="p in [{ label:'精细', size:150, overlap:30 }, { label:'标准', size:220, overlap:30 }, { label:'粗粒度', size:350, overlap:60 }]" :key="p.size" class="chip" :class="{ on:size === p.size }" :disabled="saving" @click="size = p.size; overlap = p.overlap">{{ p.label }}</button></div></div>
        <div class="hint-box"><AppIcon name="info" :size="14" /><div>按句号、问号、分号与换行优先切分；超长句按字符截断。点击「保存切块结果」后才会写入知识库。</div></div>
        <button class="btn primary block lg" :disabled="!doc || saving || loading || !!error || !chunks.length" @click="save"><AppIcon name="scissors" :size="15" /> {{ saving ? '正在保存…' : '保存切块结果' }}</button>
        <RouterLink v-if="committed" class="btn block" style="margin-top:10px" to="/vector">下一步：向量入库</RouterLink>
        <p v-if="committed" class="hint" style="margin-top:12px">已保存到数据库，可在文档详情核对原文。可继续前往向量入库。</p>
      </div>
      <div class="card" :aria-busy="loading"><div class="card-head"><b>切块预览</b><span id="chunkStat" class="sub">{{ loading ? '正在生成预览…' : doc ? `预计 ${chunks.length} 段 · 平均 ${average} 字` : '未选择文档' }}</span></div>
        <div v-if="loading" class="knowledge-loading" role="status"><span class="spinner"></span> 正在预览…</div>
        <ChunkPreviewList v-else-if="doc && chunks.length" :chunks="chunks" :doc="doc" :overlap="overlap" />
        <EmptyState v-else icon="scissors" title="暂无切块预览" description="请选择已解析的文档，或重试加载。" />
      </div>
    </div>
  </div>
</template>
