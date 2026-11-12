<script setup lang="ts">
import {computed} from 'vue'
import {useRoute} from 'vue-router'
import {authApi,currentAccount} from '../../api/auth'
import {roleNavigation,roleNames,type RoleLink} from '../../config/roleNavigation'
const route=useRoute()
const links=computed(()=>roleNavigation[currentAccount.value?.role||'']||[])
const roleName=computed(()=>roleNames[currentAccount.value?.role||'']||'工作台')
const avatarInitial=computed(()=>currentAccount.value?.name?.trim().slice(0,1)||'禾')
function destination(link:RoleLink){return {path:link.path,query:{...(link.tab?{tab:link.tab}:{}),...(link.task?{task:link.task}:{})}}}
function active(link:RoleLink){if(link.path==='/residents')return route.path.startsWith('/residents');return route.path===link.path&&(!link.tab||String(route.query.tab|| (currentAccount.value?.role==='admin'?'dashboard':'tasks'))===link.tab)&&(!link.task||String(route.query.task||'incident')===link.task)}
async function logout(){try{await authApi.logout()}catch{}finally{window.location.hash='/login';window.location.reload()}}
</script>
<template><aside id="sidebar" class="sidebar caregiver-sidebar"><div class="caregiver-scroll"><section class="caregiver-identity" aria-label="当前岗位账号"><div class="caregiver-avatar" aria-hidden="true">{{ avatarInitial }}</div><h2>{{ currentAccount?.name||'欢迎您' }}</h2><span class="caregiver-role"><span></span>{{ roleName }}工作台</span></section><div class="caregiver-note"><AppIcon name="shield" :size="20"/><div><b>各司其职，照护相连</b><p>只展示当前岗位的职责功能。</p></div></div><nav class="caregiver-nav" :aria-label="roleName+'业务导航'"><RouterLink v-for="link in links" :key="link.label" :to="destination(link)" class="caregiver-nav-item" :class="{selected:active(link)}" :aria-current="active(link)?'page':undefined" :title="link.label"><AppIcon :name="link.icon" :size="21"/><span>{{ link.label }}</span></RouterLink></nav></div><div class="caregiver-footer"><span class="caregiver-footer-note">禾龄通 · 六岗位协作</span><button type="button" class="caregiver-nav-item" title="退出登录" @click="logout"><AppIcon name="arrow" :size="20"/><span>退出登录</span></button></div></aside></template>
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
