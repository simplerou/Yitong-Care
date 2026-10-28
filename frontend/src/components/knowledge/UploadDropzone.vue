<script setup lang="ts">
import { ref } from 'vue'
import { useDemoStore } from '../../stores/demo'
const store = useDemoStore(), fileInput = ref<HTMLInputElement>(), dragging = ref(false)
function pick() { fileInput.value?.click() }
function changed(event: Event) { const target = event.target as HTMLInputElement; if (target.files?.[0]) void store.upload(target.files[0]); target.value = '' }
function drop(event: DragEvent) { dragging.value = false; if (event.dataTransfer?.files[0]) void store.upload(event.dataTransfer.files[0]) }
defineExpose({ pick })
</script>
<template><div class="card upload-card"><div id="dropzone" class="dropzone" :class="{over:dragging}" role="button" tabindex="0" aria-label="选择或拖拽上传文档" @click="pick" @keydown.enter.prevent="pick" @keydown.space.prevent="pick" @dragover.prevent="dragging=true" @dragenter.prevent="dragging=true" @dragleave.prevent="dragging=false" @drop.prevent="drop"><span class="dz-ico"><AppIcon name="upload" :size="20"/></span><div class="dz-text"><b>拖拽文件到这里，或点击选择文件</b><span>支持 PDF / Word / TXT / Markdown，单个文件不超过 50MB · 上传后自动解析正文</span></div></div><div class="upload-actions"><button class="btn primary" @click="pick"><AppIcon name="plus" :size="14"/> 选择文件</button><button class="btn" @click="store.loadDemo">载入示例</button></div><input id="fileInput" ref="fileInput" type="file" accept=".pdf,.doc,.docx,.txt,.md,.markdown" hidden @change="changed"></div></template>
