<script setup lang="ts">
import { computed } from 'vue'
import { isAdmin, isResident, isCaregiver, currentAccount, authApi } from '../../api/auth'
import { useRoute } from 'vue-router'
import { menuGroups } from '../../config/menu'
import { useKnowledgeStore } from '../../stores/knowledge'
import { useRetrievalStore } from '../../stores/retrieval'
import { useOverlay } from '../../composables/useOverlay'
const route = useRoute(), ui = useOverlay()
const knowledge = useKnowledgeStore(), retrieval = useRetrievalStore()
const isProfessional = computed(()=>['medical','kitchen','nursing','finance'].includes(currentAccount.value?.role || ''))
const roleNames:Record<string,string>={medical:'医务室',kitchen:'食堂',nursing:'护理部',finance:'财务部',user:'护工'}
const visibleGroups = computed(() => menuGroups.map(group => ({...group, items: group.items.filter(item => (!isProfessional.value || item.name==='operations') && (!item.meta?.adminOnly || isAdmin.value) && (!item.meta?.staffOnly || !isResident.value) && (!item.meta?.residentOnly || isResident.value))})).filter(group => group.items.length))
const avatarInitial = computed(() => currentAccount.value?.name?.trim().slice(0,1) || '护')
async function logout(){try{await authApi.logout()}finally{window.location.hash='/login';window.location.reload()}}
function count(name: unknown) { if (name === 'kb') return knowledge.error ? '—' : knowledge.stats.documents; if (name === 'chunk') return knowledge.error ? '—' : knowledge.stats.chunks; if (name === 'vector') return knowledge.error ? '—' : knowledge.stats.vectors; if (name === 'records') return retrieval.logsError ? '—' : retrieval.total; return null }
</script>
<template>
<aside v-if="isCaregiver || isProfessional" id="sidebar" class="sidebar caregiver-sidebar">
  <div class="caregiver-scroll">
    <section class="caregiver-identity" aria-label="当前护工账号">
      <div class="caregiver-avatar" aria-hidden="true">{{ avatarInitial }}</div>
      <h2>{{ currentAccount?.name || '护工' }}</h2>
      <span class="caregiver-role"><span></span>{{ roleNames[currentAccount?.role||'user'] }}工作台</span>
    </section>
    <div class="caregiver-note"><AppIcon name="shield" :size="20"/><div><b>用心照护每一位老人</b><p>从档案核对开始，做好日常照护。</p></div></div>
    <nav class="caregiver-nav" aria-label="护工业务导航">
      <RouterLink v-if="isCaregiver" to="/operations" class="caregiver-nav-item" :class="{selected:route.path==='/operations'}" :aria-current="route.path==='/operations'?'page':undefined" title="工作概览"><AppIcon name="home" :size="21"/><span>工作概览</span></RouterLink>
      <RouterLink v-if="isCaregiver" to="/residents" class="caregiver-nav-item" :class="{selected:route.path.startsWith('/residents')}" :aria-current="route.path.startsWith('/residents')?'page':undefined" title="负责老人"><AppIcon name="clipboard" :size="21"/><span>负责老人</span></RouterLink>
      <RouterLink v-if="isProfessional" to="/operations" class="caregiver-nav-item" :class="{selected:route.path==='/operations'}" :aria-current="route.path==='/operations'?'page':undefined" title="岗位协作"><AppIcon name="shield" :size="21"/><span>岗位协作</span></RouterLink>
    </nav>
  </div>
  <div class="caregiver-footer"><span class="caregiver-footer-note">养老院 · 照护服务</span><button type="button" class="caregiver-nav-item" title="退出登录" @click="logout"><AppIcon name="arrow" :size="20"/><span>退出登录</span></button></div>
</aside>
<aside v-else id="sidebar" class="sidebar"><nav class="side-scroll" aria-label="主导航"><div v-for="group in visibleGroups" :key="group.title" class="side-group"><div class="side-label">{{ group.title }}</div><RouterLink v-for="item in group.items" :key="item.path" class="nav-item" :class="{active: route.path === item.path}" :to="item.path" :style="{'--tint': String(item.meta?.tint || ''), '--c': String(item.meta?.color || '')}"><span class="nav-ico"><AppIcon :name="String(item.meta?.icon)" :size="16"/></span><span class="nav-txt">{{ item.name==='residents' && isCaregiver ? '负责老人' : item.meta?.title }}</span><span v-if="count(item.name) !== null" class="nav-num">{{ count(item.name) }}</span></RouterLink></div></nav><div class="side-foot"><div v-if="isAdmin" class="engine-card"><div class="engine-head"><span class="live-dot"></span>知识库管理</div><p>{{ knowledge.error ? '后端暂不可用' : `文档 ${knowledge.stats.documents} 份 · 文本块 ${knowledge.stats.chunks} 段` }}<br>混合检索 · 岗位协作与审批</p><div class="engine-bars"><i v-for="n in 6" :key="n"></i></div></div><button class="side-help" @click="ui.open({kind:'help', title:'原型使用说明', subtitle:'禾龄通 · 智能养老服务平台 v0.1'})"><AppIcon name="info" :size="13"/> 使用说明 / 菜单地图</button></div></aside></template>

<style scoped>
.caregiver-sidebar{width:264px;background:#fafbfe;border-right:1px solid var(--line);}
.caregiver-scroll{flex:1;min-height:0;overflow-y:auto;padding:32px 20px 20px;}
.caregiver-identity{padding:0 14px 28px;}
.caregiver-avatar{display:grid;place-items:center;width:72px;height:72px;border-radius:50%;background:linear-gradient(135deg,#97d9ed,#b4b5f5);color:#243b7b;font-size:28px;font-weight:600;}
.caregiver-identity h2{margin:18px 0 10px;font-size:20px;line-height:1.4;overflow-wrap:anywhere;}
.caregiver-role{display:inline-flex;align-items:center;gap:7px;padding:5px 10px;border:1px solid #dae2f5;border-radius:6px;color:var(--brand-deep);font-size:12px;}
.caregiver-role>span{width:6px;height:6px;border-radius:50%;background:var(--brand);}
.caregiver-note{display:flex;align-items:flex-start;gap:10px;padding:16px 14px;margin-bottom:28px;border-radius:12px;background:linear-gradient(130deg,#eaf1ff,#f0edff);color:var(--brand-deep);}
.caregiver-note>svg{flex:none;margin-top:2px;}.caregiver-note b{font-size:13px;line-height:1.6;}.caregiver-note p{margin:7px 0 0;font-size:12px;line-height:1.8;color:#526481;}
.caregiver-nav{display:grid;gap:10px;}.caregiver-nav-item{display:flex;align-items:center;gap:16px;width:100%;min-height:54px;padding:12px 18px;box-sizing:border-box;border:0;border-radius:10px;background:transparent;color:#475569;text-decoration:none;font:inherit;font-size:15px;font-weight:600;cursor:pointer;transition:background .15s,color .15s;}
.caregiver-nav-item>svg{flex:none;color:var(--brand);}.caregiver-nav-item:hover{background:#eef2fa;color:var(--brand-deep);}.caregiver-nav-item.selected{background:#e9edfc;color:var(--brand-deep);}.caregiver-nav-item:focus-visible{outline:2px solid var(--brand);outline-offset:3px;}
.caregiver-footer{padding:18px 20px;border-top:1px solid var(--line);}.caregiver-footer-note{display:block;padding:0 18px 10px;color:#64748b;font-size:12px;}
@media(max-width:900px){.caregiver-sidebar{width:76px;}.caregiver-scroll{padding:22px 10px;}.caregiver-identity{padding:0 0 24px;display:flex;justify-content:center;}.caregiver-avatar{width:44px;height:44px;font-size:20px;}.caregiver-identity h2,.caregiver-role,.caregiver-note,.caregiver-nav-item span,.caregiver-footer-note{display:none;}.caregiver-nav-item{justify-content:center;padding:12px;}.caregiver-footer{padding:12px 10px;}}
@media(prefers-reduced-motion:reduce){.caregiver-nav-item{transition:none;}}
</style>
