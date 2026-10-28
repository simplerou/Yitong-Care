<script setup lang="ts">
import { ref } from 'vue'
const props=defineProps<{ busy: boolean }>(), emit=defineEmits<{send:[text:string]}>(), text=ref('')
function send() { if (props.busy || !text.value.trim()) return; emit('send',text.value);text.value='' }
function key(event:KeyboardEvent) { if (event.key==='Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault();send()} }
</script>
<template><div class="composer"><div class="composer-box"><textarea id="chatInput" v-model="text" rows="1" aria-label="描述您的问题" placeholder="请描述您的问题，例如：最近血压有点高，饮食上要注意什么？" :style="{height:Math.min(110,Math.max(38, text.split('\n').length*22+16))+'px'}" @keydown="key"></textarea><div class="composer-foot"><span class="composer-hint">Enter 发送 · Shift + Enter 换行 · 回答可核对原文</span><button id="sendBtn" class="send-btn" :disabled="busy" title="发送" aria-label="发送问题" @click="send"><AppIcon name="send" :size="16"/></button></div></div></div></template>
