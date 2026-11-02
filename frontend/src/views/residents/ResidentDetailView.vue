<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { isAdmin } from '../../api/auth'
import { residentsApi, emptyResident, type ResidentInput, type Resident, type ResidentChange } from '../../api/residents'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import PageHeader from '../../components/common/PageHeader.vue'
import AppSelect from '../../components/common/AppSelect.vue'
const route=useRoute(),router=useRouter(),creating=computed(()=>route.name==='resident-new')
const form=reactive<ResidentInput>(emptyResident()),record=ref<Resident|null>(null),assignees=ref<{id:string;name:string;phone_hint:string}[]>([])
const loading=ref(true),saving=ref(false),loaded=ref(false),error=ref(''),notice=ref(''),reason=ref(''),changes=ref<ResidentChange[]>([]),historyPage=ref(1),historyError=ref('')
const today=new Date().toLocaleDateString('sv-SE')
let generation=0,baseline=''
const dirty=computed(()=>loaded.value && JSON.stringify(form)!==baseline)
const confirmLeave=()=>!dirty.value || (!saving.value && window.confirm('档案修改尚未保存，确定离开吗？'))
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate(confirmLeave)
type TextKey=Exclude<keyof ResidentInput,'assigned_account_ids'|'birth_date'|'admission_date'>
const notes:{key:TextKey;label:string;hint:string}[]=[{key:'allergies',label:'过敏情况',hint:'如已核实无过敏，请明确填写；未知则留空'},{key:'chronic_conditions',label:'慢病与既往情况',hint:'填写已知情况与相关依据，不自行诊断'},{key:'dietary_notes',label:'饮食与吞咽注意事项',hint:'饮食禁忌、食物质地、进食协助等'},{key:'mobility_notes',label:'行动与辅助情况',hint:'步行、轮椅、移位及防跌倒注意事项'},{key:'communication_notes',label:'沟通与情绪观察',hint:'听力、表达、沟通习惯等已知情况'},{key:'care_notes',label:'其他照护要点',hint:'需要交代的日常照护事项'}]
function apply(row:Resident){record.value=row;for(const key of Object.keys(emptyResident()) as (keyof ResidentInput)[])Object.assign(form,{[key]:row[key]});baseline=JSON.stringify(form);reason.value=''}
async function history(more=false){historyError.value='';try{const next=more?historyPage.value+1:1;const result=await residentsApi.changes(String(route.params.id),next);changes.value=more?[...changes.value,...result.items]:result.items;historyPage.value=next}catch(e){historyError.value=e instanceof Error?e.message:'变更记录加载失败'}}
async function load(){const token=++generation;loading.value=true;loaded.value=false;error.value='';notice.value='';record.value=null;changes.value=[];historyError.value='';Object.assign(form,emptyResident());reason.value=''
 try{const [row,staff]=await Promise.all([creating.value?Promise.resolve(null):residentsApi.detail(String(route.params.id)),isAdmin.value?residentsApi.assignees():Promise.resolve([])]);if(token!==generation)return;assignees.value=staff;if(row)apply(row);else baseline=JSON.stringify(form);loaded.value=true;if(row&&isAdmin.value)await history()}
 catch(e){if(token===generation)error.value=e instanceof Error?e.message:'加载失败'}finally{if(token===generation)loading.value=false}}
async function save(){if(saving.value)return;saving.value=true;error.value='';notice.value=''
 try{const payload={...form,name:form.name.trim(),source:form.source.trim(),birth_date:form.birth_date||null,admission_date:form.admission_date||null,assigned_account_ids:[...form.assigned_account_ids]};const row=creating.value?await residentsApi.create(payload):await residentsApi.update(record.value!.id,payload,record.value!.version,reason.value.trim());apply(row);if(creating.value){await router.replace(`/residents/${row.id}`)}else{notice.value='档案已保存，变更记录已留存。';await history()}}
 catch(e){error.value=e instanceof Error?e.message:'保存失败'}finally{saving.value=false}}
watch(()=>route.fullPath,()=>void load(),{immediate:true})
function reload(){if(!dirty.value || window.confirm('重新加载会放弃未保存修改，是否继续？'))void load()}
const labels:Record<string,string>={name:'姓名',gender:'性别',birth_date:'出生日期',admission_date:'入住日期',status:'入住状态',location:'房间/床位',care_level:'照护安排',contact_name:'联系人',contact_relation:'关系',contact_phone:'联系电话',source:'信息来源',assigned_account_ids:'负责人员',...Object.fromEntries(notes.map(field=>[field.key,field.label]))}
function changeValue(key:string,value:unknown){if(value==null || value==='')return '未记录';if(key==='assigned_account_ids' && Array.isArray(value))return value.map(id=>assignees.value.find(person=>person.id===id)?.name || `账号 ${String(id).slice(0,8)}`).join('、') || '未分配';if(key==='gender')return ({male:'男',female:'女',unknown:'未记录'} as Record<string,string>)[String(value)] || String(value);if(key==='status')return value==='in_care'?'在院':'已离院';return String(value)}
function differences(change:ResidentChange){return (Object.keys(emptyResident()) as (keyof ResidentInput)[]).filter(key=>JSON.stringify(change.before?.[key])!==JSON.stringify(change.after[key])).map(key=>({label:labels[key],before:changeValue(key,change.before?.[key]),after:changeValue(key,change.after[key])}))}
function stamp(value:string){return new Date(value.endsWith('Z')?value:value+'Z').toLocaleString('zh-CN',{hour12:false})}
</script>
<template><div class="page residents"><AppBreadcrumb/><PageHeader :title="creating?'新建老人档案':record?.name || '老人档案'" :subtitle="record?`${record.record_no} · 档案版本 ${record.version}`:'从基本信息开始，逐步完善照护资料。'"><RouterLink class="btn" to="/residents">返回列表</RouterLink></PageHeader>
 <p v-if="loading" class="resident-empty" role="status">正在加载档案…</p><div v-if="error" class="resident-error" role="alert">{{ error }} <button type="button" class="btn" :disabled="saving" @click="reload">重新加载</button></div><p v-if="notice" class="resident-notice" role="status">{{ notice }}</p>
 <form v-if="loaded" @submit.prevent="save"><fieldset :disabled="saving || !isAdmin" class="resident-fieldset"><section class="card resident-section"><h2>基本与入住信息</h2><p class="resident-helper">姓名、信息来源为必填。其余信息可以稍后补充，留空表示未记录。</p><div class="resident-form-grid">
 <label for="r-name">姓名（必填）<input id="r-name" v-model="form.name" class="input" required maxlength="50" autocomplete="off"></label>
 <label for="r-gender">性别<AppSelect id="r-gender" v-model="form.gender" class="select" :disabled="saving || !isAdmin"><option value="unknown">未记录</option><option value="male">男</option><option value="female">女</option></AppSelect></label>
 <label for="r-birth">出生日期<input id="r-birth" v-model="form.birth_date" class="input" type="date" :max="today"></label>
 <label for="r-admission">实际入住日期<input id="r-admission" v-model="form.admission_date" class="input" type="date" :min="form.birth_date || undefined" :max="today"></label>
 <label for="r-status">入住状态<AppSelect id="r-status" v-model="form.status" class="select" :disabled="saving || !isAdmin"><option value="in_care">在院</option><option value="discharged">已离院</option></AppSelect></label>
 <label for="r-location">房间 / 床位登记<input id="r-location" v-model="form.location" class="input" maxlength="100" placeholder="如：1号楼 / 201室 / 02床"></label>
 <label for="r-care">照护安排<AppSelect id="r-care" v-model="form.care_level" class="select" :disabled="saving || !isAdmin"><option v-for="level in ['未评估','自理','部分协助','全面协助','专人照护']" :key="level" :value="level">{{ level }}</option></AppSelect></label>
 <label for="r-source">信息来源（必填）<input id="r-source" v-model="form.source" class="input" required maxlength="200" placeholder="如：家属提供的入住资料，登记日期…"></label></div><p class="resident-helper">床位目前为位置登记，尚未提供床位占用检查或调床流程。照护安排为人工登记，不是自动评估结论。</p></section>
 <section class="card resident-section"><h2>紧急联系人</h2><div class="resident-form-grid"><label for="r-contact">联系人姓名<input id="r-contact" v-model="form.contact_name" class="input" maxlength="50" autocomplete="off"></label><label for="r-relation">与老人关系<input id="r-relation" v-model="form.contact_relation" class="input" maxlength="30" placeholder="如：女儿、配偶"></label><label for="r-phone">联系电话<input id="r-phone" v-model="form.contact_phone" class="input" type="tel" maxlength="32" placeholder="手机或固定电话" autocomplete="off"></label></div></section>
 <section class="card resident-section"><h2>健康与照护要点</h2><div class="resident-form-grid"><label v-for="field in notes" :key="field.key" :for="`r-${field.key}`">{{ field.label }}<textarea :id="`r-${field.key}`" v-model="form[field.key]" class="input" rows="3" :maxlength="field.key==='care_notes'?4000:2000" :placeholder="isAdmin?field.hint:'未记录'"></textarea></label></div></section>
 <section v-if="isAdmin" class="card resident-section"><h2>负责人员</h2><p class="resident-helper">勾选后，该工作人员即可查看本档案；取消后收回访问权限。管理员始终可管理档案。</p><p v-if="!assignees.length" class="resident-helper">暂无可分配的工作人员账号。可以先保存档案，待账号注册后再分配。</p><div class="resident-assignees"><label v-for="person in assignees" :key="person.id"><input v-model="form.assigned_account_ids" type="checkbox" :value="person.id"><span>{{ person.name }}<small>{{ person.phone_hint }}</small></span></label></div></section>
 <section v-if="isAdmin && !creating" class="card resident-section"><label for="r-reason">本次修改原因（必填）<input id="r-reason" v-model="reason" class="input" required maxlength="300" placeholder="说明修改了什么、核对依据是什么"></label></section>
 <div v-if="isAdmin" class="resident-save"><span>{{ creating?'保存后自动生成档案编号。':'变更将记录操作人、时间及前后内容。' }}</span><button class="btn primary" type="submit" :disabled="saving">{{ saving?'正在保存…':creating?'创建档案':'保存修改' }}</button></div></fieldset></form>
 <section v-if="loaded && isAdmin && !creating" class="card resident-section"><h2>档案变更记录</h2><p v-if="historyError" class="resident-error" role="alert">{{ historyError }}</p><ol class="resident-history"><li v-for="change in changes" :key="change.id"><b>{{ change.reason }}</b><p>{{ change.actor_name }} · {{ stamp(change.created_at) }} · 版本 {{ change.after.version }}</p><details><summary>查看变更内容</summary><dl class="resident-diff"><template v-for="item in differences(change)" :key="item.label"><dt>{{ item.label }}</dt><dd><span>原：{{ item.before }}</span><span>现：{{ item.after }}</span></dd></template></dl></details></li></ol><button v-if="changes.length && changes.length%10===0" class="btn" type="button" @click="history(true)">更早记录</button></section>
</div></template>
<style src="../../styles/residents.css"></style>
