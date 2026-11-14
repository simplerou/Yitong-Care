<script setup lang="ts">
import {onMounted,onBeforeUnmount,ref} from 'vue'
import AppSelect from '../../components/common/AppSelect.vue'
import {reviews,roleNames,type ReviewRecord} from '../../api/accountReviews'
const rows=ref<ReviewRecord[]>([]),result=ref('all'),page=ref(1),total=ref(0),pageSize=ref(20),loading=ref(false),error=ref('')
let generation=0
async function load(reset=false){
 if(reset)page.value=1
 const current=++generation
 loading.value=true;error.value='';rows.value=[]
 try{const data=await reviews.history(result.value,page.value);if(current!==generation)return;rows.value=data.items;total.value=data.total;pageSize.value=data.page_size}
 catch(e){if(current===generation){total.value=0;error.value=e instanceof Error?e.message:'审核记录读取失败'}}
 finally{if(current===generation)loading.value=false}
}
function dateText(value:string){return new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value)?value:value+'Z').toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'})}
onMounted(()=>void load())
onBeforeUnmount(()=>generation++)
</script>
<template><section class="review-history" aria-label="注册审核记录" :aria-busy="loading">
 <div class="card account-review-toolbar"><label>审核结果<AppSelect v-model="result" class="select" :disabled="loading" @change="load(true)"><option value="all">全部结果</option><option value="approve">已通过</option><option value="reject">未通过</option></AppSelect></label><button class="btn" :disabled="loading" @click="load()">刷新记录</button><span aria-live="polite">共 {{ total }} 条记录</span></div>
 <p class="history-help">按审核时间从新到旧展示。重新申请会保留之前的审核记录，账号停用或恢复不改变原审核结果。</p>
 <p v-if="error" class="history-error" role="alert">{{ error }} <button class="btn" :disabled="loading" @click="load()">重新加载</button></p>
 <p v-if="loading" class="card history-empty" role="status">正在读取审核记录…</p>
 <p v-else-if="!error&&!rows.length" class="card history-empty">{{ result==='all'?'暂无注册审核记录，处理申请后会在这里显示。':'暂无符合该审核结果的记录，可切换为“全部结果”查看。' }}</p>
 <div v-else class="history-list"><article v-for="record in rows" :key="record.id" class="card history-record"><header><div><h2>{{ record.applicant_name }}</h2><span class="history-help">{{ record.phone_hint }}</span></div><span class="history-result" :class="record.result">{{ record.result==='approve'?'已通过':'未通过' }}</span></header>
 <dl><div><dt>申请岗位</dt><dd>{{ roleNames[record.requested_role||'']||'未记录' }}</dd></div><div><dt>授予岗位</dt><dd>{{ record.result==='approve'?(roleNames[record.granted_role||'']||'未记录'):'未授予' }}</dd></div><div><dt>审核人</dt><dd>{{ record.reviewer_name }}</dd></div><div><dt>审核时间（北京时间）</dt><dd>{{ dateText(record.reviewed_at) }}</dd></div></dl>
 <p class="history-note"><b>审核意见</b>{{ record.note||'未填写意见' }}</p>
 <details v-if="record.application_note||record.qualification||record.valid_until||record.application_version"><summary>查看申请与资质记录</summary><p v-if="record.application_version">本次审核申请版本：{{ record.application_version }}</p><p v-if="record.application_note">申请说明：{{ record.application_note }}</p><p v-if="record.qualification">任职核实记录：{{ record.qualification }}</p><p v-if="record.valid_until">资质有效期：{{ record.valid_until }}</p></details>
 </article></div>
 <nav v-if="!error" class="history-pagination" aria-label="审核记录分页"><button class="btn" :disabled="page<=1||loading" @click="page--;load()">上一页</button><span>第 {{ page }} / {{ Math.max(1,Math.ceil(total/pageSize)) }} 页</span><button class="btn" :disabled="page*pageSize>=total||loading" @click="page++;load()">下一页</button></nav>
</section></template>
<style scoped>
.history-help{color:#526481;line-height:1.8}.history-list{display:grid;gap:16px}.history-record{padding:24px;min-width:0;overflow-wrap:anywhere}.history-record header{display:flex;align-items:center;justify-content:space-between;gap:16px}.history-record h2{font-size:18px;margin:0 0 6px}.history-result{padding:6px 12px;border-radius:8px;flex:none;font-size:14px;background:#fff0f0;color:#a12d2d}.history-result.approve{background:#eaf8f0;color:#24613e}dl{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:20px;margin:22px 0}dt{font-size:13px;color:#526481;margin-bottom:8px}dd{margin:0;line-height:1.7}.history-note{padding:16px;background:var(--bg,#f5f7fc);border-radius:10px;white-space:pre-wrap;line-height:1.8}.history-note b{display:block;margin-bottom:4px}.history-record details{margin-top:16px}.history-record summary{cursor:pointer;min-height:44px;display:flex;align-items:center;color:var(--brand-deep)}.history-record details p{line-height:1.8;white-space:pre-wrap}.history-empty,.history-error{padding:24px;line-height:1.8}.history-error{background:#fff0f0;color:#a12d2d;border-radius:10px}.history-pagination{display:flex;gap:16px;align-items:center;justify-content:center;margin:24px 0}.btn{min-height:44px}:focus-visible{outline:2px solid var(--brand);outline-offset:3px}@media(max-width:900px){dl{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:520px){dl{grid-template-columns:1fr}.history-record{padding:18px}}
</style>

<style src="../../styles/account-review-toolbar.css"></style>
