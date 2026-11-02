<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { isAdmin } from '../../api/auth'
import { residentsApi, type ResidentSummary } from '../../api/residents'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import PageHeader from '../../components/common/PageHeader.vue'
import AppSelect from '../../components/common/AppSelect.vue'
const rows=ref<ResidentSummary[]>([]),total=ref(0),page=ref(1),query=ref(''),status=ref(''),loading=ref(false),error=ref('')
const pageSize=ref(20)
const pageCount=computed(()=>Math.max(1,Math.ceil(total.value/pageSize.value)))
let generation=0
async function load(reset=false) {
  if(reset)page.value=1
  const token=++generation;loading.value=true;error.value=''
  try {const result=await residentsApi.list(query.value.trim(),status.value,page.value);if(token===generation){rows.value=result.items;total.value=result.total;pageSize.value=result.page_size}}
  catch(e){if(token===generation){rows.value=[];total.value=0;error.value=e instanceof Error?e.message:'读取失败'}}
  finally{if(token===generation)loading.value=false}
}
function jump(value:string|number){
  const target=Number(value)
  if(loading.value || !Number.isInteger(target) || target<1 || target>pageCount.value || target===page.value)return
  page.value=target;void load()
}
function turn(delta:number){jump(page.value+delta)}
onMounted(()=>void load())
</script>
<template><div class="page residents"><AppBreadcrumb/><PageHeader title="老人档案" :subtitle="isAdmin ? '集中维护老人的基本资料、照护要点与负责人员。' : '查看分配给您的老人资料，为照护工作做好准备。'"><RouterLink v-if="isAdmin" class="btn primary" to="/residents/new"><AppIcon name="plus" :size="16"/> 新建档案</RouterLink></PageHeader>
  <div class="resident-banner"><AppIcon name="shield" :size="22"/><div><b>{{ isAdmin?'一人一档，关爱有据可查':'仅展示您负责的老人' }}</b><p>档案中的未知情况请保留“未记录”，不要将资料缺失理解为没有风险。</p></div><span class="badge blue">{{ total }} 份档案</span></div>
  <form class="card resident-filters" @submit.prevent="load(true)"><label for="resident-search">查找老人<input id="resident-search" v-model="query" class="input" maxlength="100" placeholder="姓名、档案编号或房间位置"></label><label for="resident-status">入住状态<AppSelect id="resident-status" v-model="status" class="select"><option value="">全部状态</option><option value="in_care">在院</option><option value="discharged">已离院</option></AppSelect></label><button class="btn primary" :disabled="loading">查询</button></form>
  <div v-if="error" class="resident-error" role="alert">{{ error }} <button class="btn" @click="load()">重新加载</button></div>
  <div class="card"><div class="card-head"><b>档案列表</b><span class="sub">{{ isAdmin?'院内档案':'我的负责范围' }}</span></div><p v-if="loading" class="resident-empty" role="status">正在加载档案…</p><p v-else-if="!rows.length && !error" class="resident-empty">{{ query || status ? '没有符合条件的档案，请调整筛选。' : isAdmin?'还没有老人档案，点击“新建档案”开始登记。':'暂未分配老人，请联系管理员。' }}</p>
  <div v-else-if="rows.length" class="resident-table-wrap"><table class="resident-table"><thead><tr><th scope="col">老人 / 档案编号</th><th scope="col">性别</th><th scope="col">出生日期</th><th scope="col">房间 / 床位登记</th><th scope="col">照护安排</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead><tbody><tr v-for="row in rows" :key="row.id"><td><b>{{ row.name }}</b><small>{{ row.record_no }}</small></td><td>{{ {male:'男',female:'女',unknown:'未记录'}[row.gender] || '未记录' }}</td><td>{{ row.birth_date || '未记录' }}</td><td>{{ row.location || '未记录' }}</td><td>{{ row.care_level }}</td><td><span class="badge" :class="row.status==='in_care'?'green':''">{{ row.status==='in_care'?'在院':'已离院' }}</span></td><td><RouterLink class="btn sm" :to="`/residents/${row.id}`">查看档案</RouterLink></td></tr></tbody></table></div>
  <div class="resident-pagination"><span aria-live="polite">共 {{ total }} 份 · 第 {{ page }} / {{ pageCount }} 页</span><label for="resident-page" class="resident-page-label">跳至<AppSelect id="resident-page" :model-value="page" class="select resident-page-select" :disabled="loading || total===0" @change="jump"><option v-for="number in pageCount" :key="number" :value="number">第 {{ number }} 页</option></AppSelect></label><button class="btn" :disabled="loading||page<=1" @click="turn(-1)">上一页</button><button class="btn" :disabled="loading||page>=pageCount" @click="turn(1)">下一页</button></div></div>
</div></template>
<style src="../../styles/residents.css"></style>
