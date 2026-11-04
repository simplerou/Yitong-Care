<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { bindingApi, type ResidentBinding, type BoundAccount } from '../../api/residents'
import AppSelect from '../common/AppSelect.vue'
const props=defineProps<{residentId:string;disabled:boolean}>()
const emit=defineEmits<{saved:[]}>()
const binding=ref<ResidentBinding|null>(null),accounts=ref<BoundAccount[]>([]),query=ref(''),selected=ref(''),reason=ref(''),page=ref(1),hasMore=ref(false),loading=ref(false),saving=ref(false),error=ref('')
async function search(more=false){if(loading.value||saving.value)return;loading.value=true;error.value='';try{const next=more?page.value+1:1;const result=await bindingApi.candidates(query.value.trim(),next);accounts.value=more?[...accounts.value,...result.items]:result.items;hasMore.value=result.has_more;page.value=next}catch(e){error.value=e instanceof Error?e.message:'查询失败'}finally{loading.value=false}}
async function load(){error.value='';try{binding.value=await bindingApi.get(props.residentId);await search()}catch(e){error.value=e instanceof Error?e.message:'绑定信息加载失败'}}
async function submit(unbind=false){if(!binding.value||saving.value||props.disabled)return;if(!reason.value.trim()){error.value='请填写绑定或解绑的核对说明';return}if(!unbind&&!selected.value){error.value='请选择核对过身份的账号';return}
 if(!window.confirm(unbind?'确定解绑？该老人账号将失去本档案访问权限，且不会变为工作人员。':'请确认已线下核对账号本人和老人身份。绑定后该账号将成为老人账号，并需要重新登录。'))return
 saving.value=true;error.value='';try{await bindingApi.set(props.residentId,unbind?null:selected.value,binding.value.version,reason.value.trim());emit('saved')}catch(e){error.value=e instanceof Error?e.message:'保存失败'}finally{saving.value=false}}
onMounted(()=>void load())
</script>
<template><section class="card resident-section"><h2>老人登录账号</h2><p class="resident-helper">先由老人注册账号，再核对手机号和档案身份后绑定。一份档案只能绑定一个账号，账号不能同时绑定其他老人；已有工作人员负责范围的账号不能转换。</p>
 <p v-if="binding" class="resident-binding-current"><b>当前绑定：</b>{{ binding.account ? `${binding.account.name} · ${binding.account.phone_hint}` : '尚未绑定' }}</p>
 <p v-if="disabled" class="resident-helper">请先保存或放弃上方档案修改，再调整账号绑定。</p>
 <div v-if="error" class="resident-error" role="alert">{{ error }} <button class="btn" type="button" :disabled="saving||loading" @click="load">重新加载</button></div>
 <fieldset class="resident-fieldset" :disabled="disabled||saving"><div class="resident-binding-search"><label for="binding-query">查找已有账号<input id="binding-query" v-model="query" class="input" maxlength="100" placeholder="输入姓名或手机号" @keydown.enter.prevent="search()"></label><button class="btn" type="button" :disabled="loading" @click="search()">{{ loading?'查询中…':'查找账号' }}</button></div>
 <div class="resident-form-grid"><label for="binding-account">选择待绑定账号<AppSelect id="binding-account" v-model="selected" class="select" :disabled="disabled||saving||loading"><option value="">请选择已核对的账号</option><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name }} · {{ account.phone_hint }}</option></AppSelect></label><label for="binding-reason">身份核对 / 解绑说明<input id="binding-reason" v-model="reason" class="input" maxlength="200" placeholder="记录核对方式或解绑原因"></label></div>
 <button v-if="hasMore" class="btn" type="button" :disabled="loading" @click="search(true)">更多账号</button><p v-if="!loading&&!accounts.length" class="resident-helper">没有符合条件的可绑定账号。已绑定其他老人、管理员或已分配照护职责的账号不会出现在这里。</p>
 <div class="resident-binding-actions"><button class="btn primary" type="button" :disabled="!binding||loading" @click="submit(false)">{{ saving?'正在保存…':binding?.account?'更换绑定':'确认绑定' }}</button><button v-if="binding?.account" class="btn" type="button" @click="submit(true)">解除绑定</button></div></fieldset>
 <p class="resident-helper">绑定、更换或解绑会撤销相关老人账号的已有登录凭证，请其重新登录。这里只建立数据关系，不创建餐食菜单或选餐记录。</p>
</section></template>
