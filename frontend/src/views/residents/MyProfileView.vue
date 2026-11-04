<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { bindingApi, type PersonalResident } from '../../api/residents'
import PageHeader from '../../components/common/PageHeader.vue'
const resident=ref<PersonalResident|null>(null),loading=ref(false),error=ref('')
async function load(){loading.value=true;error.value='';resident.value=null;try{resident.value=(await bindingApi.mine()).resident}catch(e){error.value=e instanceof Error?e.message:'读取失败'}finally{loading.value=false}}
const fields=[['allergies','过敏情况'],['chronic_conditions','健康情况'],['dietary_notes','饮食与吞咽注意事项'],['mobility_notes','行动情况'],['communication_notes','沟通情况'],['care_notes','照护要点']] as const
onMounted(()=>void load())
</script>
<template><div class="page residents resident-personal"><PageHeader title="我的健康档案" subtitle="查看与您账号绑定的本人资料，发现错误请联系工作人员核对。"><button class="btn" :disabled="loading" @click="load">刷新资料</button></PageHeader>
 <p v-if="loading" class="resident-empty" role="status">正在读取您的档案…</p><p v-else-if="error" class="resident-error" role="alert">{{ error }}</p><section v-else-if="!resident" class="card resident-section"><h2>账号尚未绑定档案</h2><p>请联系养老院管理员核实身份并绑定。您无法自行选择或认领他人的档案。</p></section>
 <template v-else><section class="resident-banner"><AppIcon name="heart" :size="28"/><div><h2>{{ resident.name }}</h2><p>{{ resident.record_no }} · {{ resident.location || '位置未记录' }}</p></div><span class="badge blue">本人档案</span></section><section class="card resident-section"><h2>基本信息</h2><dl class="resident-personal-info"><dt>性别</dt><dd>{{ {male:'男',female:'女',unknown:'未记录'}[resident.gender] || '未记录' }}</dd><dt>出生日期</dt><dd>{{ resident.birth_date || '未记录' }}</dd><dt>实际入住日期</dt><dd>{{ resident.admission_date || '未记录' }}</dd><dt>入住状态</dt><dd>{{ resident.status==='in_care'?'在院':'已离院' }}</dd><dt>照护安排</dt><dd>{{ resident.care_level }}</dd></dl></section><section v-for="[key,label] in fields" :key="key" class="card resident-section"><h2>{{ label }}</h2><p class="resident-personal-text">{{ resident[key] || '尚未记录，请联系工作人员核对。' }}</p></section><p class="resident-helper">本页为已登记资料展示，不是自动诊断或医疗建议；每日餐食与选餐请前往“我的餐食”。</p></template>
</div></template>
<style src="../../styles/residents.css"></style>
