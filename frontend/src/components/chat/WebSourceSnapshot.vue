<script setup lang="ts">
import { onMounted,onUnmounted,ref } from 'vue'
import { safeWebUrl,type WebSource } from '../../api/chat'
const props=defineProps<{source:WebSource}>(),emit=defineEmits<{close:[]}>(),dialog=ref<HTMLDialogElement>()
onMounted(()=>dialog.value?.showModal())
onUnmounted(()=>dialog.value?.close())
function backdrop(event:MouseEvent){if(event.target===dialog.value)emit('close')}
</script>
<template><Teleport to="body"><dialog ref="dialog" class="web-snapshot" aria-labelledby="policy-web-snapshot-title" @cancel.prevent="emit('close')" @click="backdrop"><header><div><span class="badge blue">保存的网页正文</span><h2 id="policy-web-snapshot-title">{{props.source.title}}</h2></div><button class="btn sm" autofocus aria-label="关闭网页正文快照" @click="emit('close')">关闭</button></header><div class="snapshot-meta"><p>获取于 {{new Date(props.source.retrieved_at).toLocaleString('zh-CN')}} · {{props.source.is_truncated?'保存的是正文节选':'保存的是当次服务提取的正文'}}，不保证附件或全文完整。</p><a :href="safeWebUrl(props.source.url)||undefined" target="_blank" rel="noopener noreferrer">打开官网当前页面 ↗</a><p class="snapshot-url">{{props.source.url}}</p></div><pre>{{props.source.content}}</pre></dialog></Teleport></template>
<style scoped>
.web-snapshot { width:min(840px,calc(100vw - 32px)); max-height:85vh; box-sizing:border-box; padding:0; border:1px solid var(--line); border-radius:14px; color:var(--ink); background:var(--surface,#fff); }
.web-snapshot[open] { display:flex; flex-direction:column; }
.web-snapshot::backdrop { background:rgb(15 23 42 / 45%); }
header { display:flex; align-items:flex-start; gap:16px; justify-content:space-between; padding:18px 20px; border-bottom:1px solid var(--line); flex-shrink:0; }
header > div { min-width:0; }
h2 { font-size:17px; line-height:1.6; margin:8px 0 0; overflow-wrap:anywhere; }
header button { flex-shrink:0; min-height:44px; }
.snapshot-meta { padding:12px 20px; font-size:12px; line-height:1.7; color:var(--muted); border-bottom:1px solid var(--line); flex-shrink:0; }
p { margin:0 0 6px; }
a { color:var(--brand); }
.snapshot-url { overflow-wrap:anywhere; max-height:4em; overflow:auto; }
pre { margin:0; padding:18px 20px; white-space:pre-wrap; overflow-wrap:anywhere; overflow:auto; font:inherit; font-size:14px; line-height:1.9; min-height:0; overscroll-behavior:contain; }
@media(max-width:600px){header,.snapshot-meta,pre{padding:12px 14px}.web-snapshot{max-height:90vh}}
</style>
