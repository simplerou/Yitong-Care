<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDemoStore } from '../../stores/demo'
import { useOverlay } from '../../composables/useOverlay'
const store = useDemoStore(), router = useRouter(), ui = useOverlay(), query = ref('')
function search() { if (!query.value.trim()) return; void router.push({path:'/search',query:{q:query.value.trim(),run:String(Date.now())}}) }
</script>
<template>
<header class="topbar">
  <RouterLink class="brand" to="/home" aria-label="颐养通首页"><span class="brand-mark"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.2 5.9a4.9 4.9 0 0 0-7 0L12 7.1l-1.2-1.2a4.9 4.9 0 1 0-7 7L12 21l8.2-8.1a4.9 4.9 0 0 0 0-7z"/></svg></span><span class="brand-text"><b>颐养通</b><small>智能养老服务平台</small></span></RouterLink>
  <div class="global-search"><AppIcon name="search" :size="17"/><input id="globalSearch" v-model="query" type="search" aria-label="搜索知识库、政策、服务" placeholder="搜索知识库、政策、服务…" autocomplete="off" @keydown.enter="search"><kbd>Enter</kbd></div>
  <div class="top-actions"><button id="seniorBtn" class="senior-btn" :aria-pressed="store.senior" title="放大字号，方便长辈使用" @click="store.toggleSenior"><span class="senior-dot"></span><span id="seniorLabel">{{ store.senior ? '标准模式' : '长辈模式' }}</span></button><button class="top-icon" title="消息通知" aria-label="消息通知" @click="ui.open({kind:'notice', title:'消息通知', subtitle:'4 条未读提醒'})"><AppIcon name="bell" :size="19"/><i class="dot"></i></button><div class="user-chip"><span class="avatar">张</span><span class="user-meta"><b>张阿姨</b><small>拱墅区 · 和睦社区</small></span></div></div>
</header>
</template>
