<script setup lang="ts">
import { computed,onMounted,onBeforeUnmount,watch,ref } from 'vue'
import { useKnowledgeStore } from '../../stores/knowledge'
import { useVectorStore } from '../../stores/vectors'
import { embeddingsApi } from '../../api/embeddings'
import { useOverlay } from '../../composables/useOverlay'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'
const knowledge=useKnowledgeStore(),store=useVectorStore(),ui=useOverlay(),loading=ref(true)
const docs=computed(()=>knowledge.choices.filter(d=>(d.chunkCount||0)>0&&!d.parsing))
const doc=computed(()=>docs.value.find(d=>d.id===knowledge.selectedDocId)),model=computed(()=>store.models[0])
const steps=['读取已保存的文本块','调用 Embedding 模型生成向量','写入向量库并建立索引']
const currentStep=computed(()=>store.task?.status==='succeeded'?3:store.task?.phase==='indexing'?2:store.task?.phase==='embedding'?1:0)
let timer:ReturnType<typeof setInterval>,polling=false,disposed=false
async function initialize(){
 loading.value=true
 try{
  await Promise.all([knowledge.loadChoices(),store.load()])
  if(disposed)return
  const tasks=await embeddingsApi.tasks(),active=tasks.find(t=>['queued','running'].includes(t.status))
  if(active){knowledge.selectedDocId=active.doc_id;store.task=active}
  else{if(!docs.value.some(d=>d.id===knowledge.selectedDocId))knowledge.selectedDocId=docs.value[0]?.id||'';if(knowledge.selectedDocId)await store.latest(knowledge.selectedDocId)}
 }catch(e){store.error=e instanceof Error?e.message:'加载文档失败。'}finally{loading.value=false}
}
watch(()=>knowledge.selectedDocId,id=>{if(id&&!loading.value)void store.latest(id)})
onMounted(()=>{void initialize();timer=setInterval(async()=>{if(store.active&&!polling){polling=true;try{await store.refresh()}finally{polling=false}}},1200)})
onBeforeUnmount(()=>{disposed=true;clearInterval(timer)})
</script>
<template><div class="page"><AppBreadcrumb/><PageHeader title="向量入库" subtitle="将已保存的文本块生成向量，保存到 MySQL，并发布 FAISS 检索索引。"><span v-if="store.status" class="badge" :class="store.status.healthy?'green':'amber'">{{store.status.healthy?'索引检查正常':'索引需要重建'}}</span></PageHeader>
<div v-if="store.error" class="knowledge-error" role="alert"><span>{{store.error}}</span><button class="btn sm" @click="initialize">重新加载</button></div>
<div v-if="loading" class="card knowledge-loading" role="status">正在加载入库信息…</div>
<div v-else-if="!docs.length&&!store.error" class="card"><EmptyState icon="database" title="还没有可入库的文本块" description="请先上传文档并保存切块结果。"><RouterLink class="btn primary" to="/chunk">去切块</RouterLink></EmptyState></div>
<div v-else class="split-2"><div class="card cfg-card"><div class="field"><label for="vecDoc">选择文档</label><select id="vecDoc" v-model="knowledge.selectedDocId" class="select" :disabled="store.active||store.busy"><option v-for="d in docs" :key="d.id" :value="d.id">{{d.name}}（{{d.chunkCount}} 段）</option></select></div>
<div class="field"><label for="vecModel">Embedding 模型</label><select id="vecModel" class="select" disabled><option v-for="m in store.models" :key="m.id">{{m.name||'尚未配置'}} · {{m.dimensions}} 维</option></select><div class="hint">使用后端已配置的模型。更换模型、服务或维度后需重新入库。</div><p v-if="model&&!model.configured" class="document-error">{{model.hint}}</p></div>
<div class="field"><label for="vecBatch">批次大小</label><select id="vecBatch" v-model.number="store.batch" class="select" :disabled="store.active||store.busy"><option v-for="n in [8,16,32]" :key="n" :value="n">{{n}} 条 / 批</option></select></div>
<div class="hint-box"><AppIcon name="info" :size="14"/><div>保存新切块后需要重新入库。执行期间采用单写者保护，完成后才发布新的索引版本。</div></div>
<button class="btn primary block lg" :disabled="!doc||!model?.configured||store.busy||store.active||store.rebuilding" @click="store.start"><AppIcon name="database" :size="15"/>{{store.active?'正在处理…':store.busy?'正在提交…':doc?.status==='vectorized'?'重新向量化':'开始向量入库'}}</button>
<div class="hint" style="text-align:center;margin-top:8px">当前文档已保存 {{doc?.vectorCount||0}} / {{doc?.chunkCount||0}} 条向量</div>
<button v-if="store.task?.status==='failed'" class="btn block" style="margin-top:10px" :disabled="store.busy" @click="store.retry">重试失败任务（继续未完成批次）</button>
<button v-else-if="store.active" class="btn block" style="margin-top:10px" :disabled="store.busy" @click="ui.confirm('恢复任务','仅在后端重启或任务中断时使用；仍在运行的任务会拒绝重复执行。',()=>{void store.retry()},'恢复任务')">恢复中断任务</button>
</div><div><div class="card run-panel"><div class="run-head"><b>入库进度</b><span class="badge" :class="store.task?.status==='succeeded'?'green':store.task?.status==='failed'?'red':''">{{store.task?.status==='succeeded'?'已完成':store.task?.status==='failed'?'失败':store.active?'处理中':'待执行'}}</span></div><div id="runPct" class="run-big">{{store.task?.progress||0}}<small>%</small></div><div class="run-sub">{{store.task?`${store.task.processed}/${store.task.total} 段 · ${store.task.model_name}`:'点击左侧按钮开始处理'}}</div><div class="progress-line" style="margin:14px 0 18px" role="progressbar" :aria-valuenow="store.task?.progress||0" aria-valuemin="0" aria-valuemax="100" aria-label="入库进度"><i :style="{width:(store.task?.progress||0)+'%'}"></i></div><div class="run-steps"><div v-for="(step,i) in steps" :key="step" class="run-step" :class="{done:currentStep>i,active:store.active&&currentStep===i}"><span class="step-dot"><AppIcon name="check" :size="10"/></span>{{step}}</div></div><div v-if="store.task?.error_message" class="document-error" role="alert">{{store.task.error_message}}</div><div id="runLog" class="run-log" aria-live="polite">{{store.task?.log.join('\n')||'等待创建向量任务。'}}</div></div>
<div class="card collection" style="padding:16px 18px"><div class="card-head" style="padding:0 0 8px;border:0"><b>向量索引概览</b><span class="sub">当前模型</span></div><div v-for="[label,value] in [['向量总数',`${store.status?.vectors||0} 条`],['向量维度',`${store.status?.dimensions||'—'} 维`],['索引类型',store.status?.index_type||'—'],['覆盖文档',`${store.status?.documents||0} 份`]]" :key="label" class="coll-row"><span>{{label}}</span><b>{{value}}</b></div><div v-for="index in store.status?.indexes||[]" :key="index.kb_id" class="coll-row"><span>{{index.kb_name}}</span><b>v{{index.version}} · {{index.indexed_vectors}} 条</b><span v-if="index.message" class="document-error">{{index.message}}</span></div><button class="btn block" style="margin-top:12px" :disabled="store.rebuilding||store.active" @click="store.rebuild">{{store.rebuilding?'正在重建…':'从数据库重建索引'}}</button></div></div></div>
</div></template>
