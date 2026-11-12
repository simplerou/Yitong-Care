<script setup lang="ts">
import { authApi, isAdmin, currentAccount } from '../../api/auth'
import { useDemoStore } from '../../stores/demo'
const store = useDemoStore()
async function logout() { try { await authApi.logout() } finally { window.location.hash = '/login'; window.location.reload() } }
</script>
<template>
<header class="topbar">
  <RouterLink class="brand" to="/operations" aria-label="禾龄通首页"><span class="brand-mark"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.2 5.9a4.9 4.9 0 0 0-7 0L12 7.1l-1.2-1.2a4.9 4.9 0 1 0-7 7L12 21l8.2-8.1a4.9 4.9 0 0 0 0-7z"/></svg></span><span class="brand-text"><b>禾龄通</b><small>智能养老服务平台</small></span></RouterLink>
  <div class="top-actions"><button id="seniorBtn" class="senior-btn" :aria-pressed="store.senior" title="放大字号，方便长辈使用" @click="store.toggleSenior"><span class="senior-dot"></span><span id="seniorLabel">{{ store.senior ? '标准模式' : '大字模式' }}</span></button><button type="button" class="user-chip" style="border:0;background:transparent;color:inherit" @click="logout"><span class="avatar"><AppIcon name="smile" :size="20"/></span><span class="user-meta"><b>{{ currentAccount?.name || '用户' }} · 退出</b><small>{{ ({admin:'院长 / 管理员',medical:'医务室',kitchen:'食堂',nursing:'护理部',finance:'财务部',user:'护工'} as Record<string,string>)[currentAccount?.role||'user'] || '账号' }}</small></span></button></div>
</header>
</template>
