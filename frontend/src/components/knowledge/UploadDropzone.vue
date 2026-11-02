<script setup lang="ts">
import { computed, ref } from 'vue'
import { useKnowledgeStore } from '../../stores/knowledge'
const props = withDefaults(defineProps<{ kbId?: string; source?: string }>(), { kbId: 'general', source: '本地上传' })
const store = useKnowledgeStore(), fileInput = ref<HTMLInputElement>(), dragging = ref(false)
const queue = computed(() => store.queue)
const uploaded = computed(() => queue.value.filter(item => item.status === 'done').length)
const failed = computed(() => queue.value.filter(item => item.status === 'error').length)
function pick() { if (!store.uploading) fileInput.value?.click() }
function upload(files?: FileList | File[] | null) {
  const list = Array.from(files || [])
  if (list.length) void store.uploadMany(list, props.kbId, props.source)
}
function changed(event: Event) {
  const target = event.target as HTMLInputElement
  upload(target.files); target.value = ''
}
function drop(event: DragEvent) { dragging.value = false; upload(event.dataTransfer?.files) }
function queueLabel(status: string) {
  return status === 'done' ? '已上传' : status === 'uploading' ? '上传中' : status === 'error' ? '失败' : '等待'
}
defineExpose({ pick })
</script>
<template>
  <div class="card upload-card">
    <div id="dropzone" class="dropzone" :class="{ over: dragging }" role="button" tabindex="0"
      :aria-disabled="store.uploading" aria-label="选择或拖拽上传文档"
      @click="pick" @keydown.enter.prevent="pick" @keydown.space.prevent="pick"
      @dragover.prevent="dragging = true" @dragenter.prevent="dragging = true"
      @dragleave.prevent="dragging = false" @drop.prevent="drop">
      <span class="dz-ico"><AppIcon name="upload" :size="20" /></span>
      <div class="dz-text"><b>{{ store.uploading ? `正在上传 ${uploaded + failed + 1 <= queue.length ? uploaded + failed + 1 : queue.length}/${queue.length}…` : '拖拽文件到这里，或点击选择文件' }}</b>
        <span>支持 PDF / DOCX / TXT / Markdown，可多选批量上传，单个文件不超过 50MB · 上传后自动解析正文</span>
      </div>
    </div>
    <div class="upload-actions">
      <button class="btn primary" :disabled="store.uploading" @click="pick"><AppIcon name="plus" :size="14" /> 选择文件</button>
      <button class="btn" :disabled="store.uploading" @click="store.loadDemo(props.kbId, '功能验证示例')">载入示例</button>
      <span v-if="queue.length" class="upload-count">已上传 {{ uploaded }} / {{ queue.length }} 份{{ failed ? `，${failed} 份失败` : '' }}</span>
      <button v-if="queue.length && !store.uploading" class="btn sm" @click="store.clearQueue()">清空列表</button>
    </div>
    <ul v-if="queue.length" class="upload-queue" aria-live="polite">
      <li v-for="item in queue" :key="item.name" :class="item.status">
        <span class="q-name" :title="item.name">{{ item.name }}</span>
        <span class="q-status">{{ queueLabel(item.status) }}</span>
        <span v-if="item.message" class="q-message">{{ item.message }}</span>
      </li>
    </ul>
    <input id="fileInput" ref="fileInput" type="file" multiple accept=".pdf,.docx,.txt,.md,.markdown" hidden @change="changed">
  </div>
</template>

<style scoped>
/* base.css 把 .upload-actions 设成竖排；批量上传需要横向工具条与整行队列。 */
.upload-card { display: block; }
.upload-card :deep(.dropzone) { width: 100%; }
.upload-actions { display: flex; flex-direction: row; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
.upload-count { margin-left: auto; color: var(--muted); font-size: 12px; }
.upload-queue { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 6px; max-height: 220px; overflow: auto; }
.upload-queue li { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border: 1px solid var(--line); border-radius: 8px; font-size: 12.5px; }
.q-name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.q-status { flex: 0 0 auto; color: var(--muted); }
.upload-queue li.done .q-status { color: #1a7f4b; }
.upload-queue li.error .q-status { color: #a52329; }
.q-message { flex: 0 1 auto; color: #a52329; overflow-wrap: anywhere; }
@media (max-width: 640px) { .upload-count { margin-left: 0; } }
</style>
