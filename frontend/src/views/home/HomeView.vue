<script setup lang="ts">
import { currentAccount, isAdmin } from '../../api/auth'
import { loadRecentConversations, type RecentConversation } from '../../api/home'
import { computed,onMounted, ref } from 'vue'
import { agents } from '../../config/agents'
import { useRetrievalStore } from '../../stores/retrieval'
import { useKnowledgeStore } from '../../stores/knowledge'
import { useDemoStore } from '../../stores/demo'
const store = useDemoStore(), s = store.state
const knowledge = useKnowledgeStore(), retrieval = useRetrievalStore()
const personalRecent = ref<RecentConversation[]>([]), recentLoading = ref(true), recentError = ref(false)
onMounted(async () => {
  if(isAdmin.value)void knowledge.load()
  try { const result = await loadRecentConversations(); personalRecent.value = result.items; recentError.value = result.failed > 0 }
  catch { recentError.value = true }
  finally { recentLoading.value = false }
})
interface Reminder { id: string; title: string; time: string; done: boolean }
const day = new Date().toLocaleDateString('sv-SE')
const reminderKey = `yitong-reminders:${currentAccount.value?.id || 'anonymous'}:${day}`
const personalReminders = ref<Reminder[]>([]), taskTitle = ref(''), taskTime = ref(''), taskError = ref('')
try { const stored = JSON.parse(localStorage.getItem(reminderKey) || '[]'); if(Array.isArray(stored))personalReminders.value = stored.filter(row => typeof row?.id === 'string' && typeof row?.title === 'string' && typeof row?.time === 'string' && typeof row?.done === 'boolean') } catch { /* Ignore unavailable or damaged local preferences. */ }
const reminders = computed(() => isAdmin.value ? s.reminders : personalReminders.value)
const pendingCount = computed(() => reminders.value.filter(row => !row.done).length)
function saveReminders() { try { localStorage.setItem(reminderKey, JSON.stringify(personalReminders.value)); taskError.value = '' } catch { taskError.value = '浏览器无法保存提醒，刷新后可能丢失。' } }
function addReminder() {
  if(!taskTitle.value.trim()) { taskError.value = '请填写提醒事项'; return }
  personalReminders.value.push({id:crypto.randomUUID(),title:taskTitle.value.trim(),time:taskTime.value || '今天',done:false})
  taskTitle.value=''; taskTime.value=''; saveReminders()
}
function openConversation(row: RecentConversation) {
  const scope = row.agentId === 'med' ? 'medication' : row.agentId
  try { localStorage.setItem(`yitong-${scope}-conversation:${currentAccount.value?.id || 'offline'}`,row.id) } catch { /* Conversation list remains available. */ }
}
function displayTime(value: string) { return new Date(value.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(value) ? value : value+'Z').toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}) }

const now = new Date(), h = now.getHours(), greet = h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 13 ? '中午好' : h < 18 ? '下午好' : '晚上好'
const date = `${now.getFullYear()}年${now.getMonth()+1}月${now.getDate()}日 星期${'日一二三四五六'[now.getDay()]}`
const stats = computed(() => [
  { icon:'book', label:'知识文档', value:knowledge.stats.documents, unit:'份', tint:'#EEF4FF', color:'#1B64F2' },
  { icon:'layers', label:'文本块', value:knowledge.stats.chunks, unit:'段', tint:'#F0EDFB', color:'#6E56CF' },
  { icon:'database', label:'向量条目', value:knowledge.stats.vectors, unit:'条', tint:'#E7F8F0', color:'#0FA968' },
  { icon:'message', label:'演示问答', value:52 + Object.values(s.chats).reduce((n,m) => n + m.filter(x => x.role === 'user').length,0) + s.history.length, unit:'次', tint:'#FDF3E0', color:'#E8930C' }
])
const pipeline = computed(() => [
  {title:'文档上传',desc:'PDF / Word / TXT',to:'/kb',stat:`${knowledge.stats.documents} 份文档`,icon:'upload'},
  {title:'文本切块',desc:'按句切分 + 重叠',to:'/chunk',stat:`${knowledge.stats.chunks} 个文本块`,icon:'scissors'},
  {title:'向量入库',desc:'Embedding + 索引',to:'/vector',stat:`${knowledge.stats.vectors} 条向量`,icon:'database'},
  {title:'向量检索',desc:'余弦相似度 TopK',to:'/search',stat:'TopK 5 · 阈值 0.12',icon:'search'},
  {title:'结果与原文',desc:'片段展示 + 出处',to:'/records',stat:`${retrieval.total} 次检索记录`,icon:'history'}
])
const agent = (id: string) => agents.find(a => a.id === id) || agents[0]
function toggle(id: string) { const r = reminders.value.find(r => r.id === id); if (r) { r.done = !r.done; if(!isAdmin.value)saveReminders(); store.notify(r.done ? '已标记完成' : '已恢复为待办') } }
</script>
<template><div class="page" style="--tint:#EEF4FF;--c:#1B64F2">
  <div class="hero"><div class="hero-main"><div v-if="isAdmin" class="hero-eyebrow"><span class="pin"></span>杭州市 · 拱墅区 · 和睦社区养老服务中心</div><h1>{{ greet }}，{{ currentAccount?.name || '欢迎您' }}</h1><p v-if="isAdmin">今天是 {{ date }}。您还有 {{ store.pendingCount }} 项健康任务待完成。想了解政策、调理饮食或身体不舒服，都可以直接问智能体。</p><p v-else>今天是 {{ date }}。从健康咨询到生活陪伴，选择智能体，开启您的专属对话。</p><div class="hero-actions"><RouterLink class="btn light lg" to="/agent/health"><AppIcon name="message" :size="16"/> 开始健康咨询</RouterLink><button class="btn glass lg" @click="store.toggleSenior"><AppIcon name="sparkles" :size="16"/> {{ store.senior ? '退出长辈模式' : '长辈模式' }}</button></div></div><div v-if="isAdmin" class="hero-side"><div class="score-ring" style="--p:86"><span>86<small>健康分</small></span></div><div class="hero-note"><div class="hn-row"><span>今日守护</span><b>{{ store.pendingCount }} 项待办</b></div><ul><li :class="{done:s.reminders[0].done}"><i></i>晨起降压药已服用</li><li :class="{done:s.reminders[1].done}"><i></i>血压待记录</li><li :class="{done:s.reminders[2].done}"><i></i>助餐已预订</li></ul></div></div></div>
  <div v-if="isAdmin" class="stat-row"><div v-for="stat in stats" :key="stat.label" class="stat"><span class="stat-ico" :style="{'--tint':stat.tint,'--c':stat.color}"><AppIcon :name="stat.icon" :size="19"/></span><div><div class="stat-val">{{ stat.value.toLocaleString('zh-CN') }}<small>{{ stat.unit }}</small></div><div class="stat-label">{{ stat.label }}</div></div></div></div>
  <div class="sec-head"><div class="sec-title">智能体服务</div><RouterLink v-if="isAdmin" class="sec-link" to="/services">服务记录 <AppIcon name="right" :size="12"/></RouterLink></div><div class="svc-grid"><RouterLink v-for="a in agents" :key="a.id" class="svc" :to="`/agent/${a.id}`" :style="{'--tint':a.tint,'--c':a.color}"><span class="svc-ico"><AppIcon :name="a.icon" :size="21"/></span><span class="svc-body"><b>{{ a.name }}</b><p>{{ a.desc }}</p><span v-if="isAdmin" class="svc-tag"><AppIcon name="database" :size="10"/> 演示知识范围 {{ a.kbNames.length }} 份资料</span></span></RouterLink></div>
  <div v-if="isAdmin" class="sec-head"><div class="sec-title">知识库与 RAG 全链路</div><span class="sec-link">文档 → 切块 → 向量 → 检索 → 原文</span></div><div v-if="isAdmin" class="pipeline"><RouterLink v-for="(p,i) in pipeline" :key="p.to" class="pipe" :to="p.to"><div class="pipe-top"><span class="pipe-num">{{ i+1 }}</span><AppIcon :name="p.icon" :size="15"/></div><h4>{{ p.title }}</h4><p>{{ p.desc }}</p><div class="pipe-stat">{{ p.stat }}</div></RouterLink></div>
  <div class="bottom-grid">
    <section class="card" aria-labelledby="today-heading"><div class="card-head"><b id="today-heading">今日守护 <span v-if="isAdmin" class="badge">演示</span></b><span class="sub">{{ pendingCount }} 项待完成</span></div>
      <form v-if="!isAdmin" class="reminder-form" @submit.prevent="addReminder"><label for="reminder-title">添加今日提醒</label><input id="reminder-title" v-model="taskTitle" class="input" maxlength="80" placeholder="例如：晚饭后散步" :aria-invalid="!!taskError" :aria-describedby="taskError ? 'reminder-error' : undefined"><div class="reminder-controls"><label for="reminder-time">时间（选填）</label><input id="reminder-time" v-model="taskTime" class="input" type="time"><button class="btn primary" type="submit">添加提醒</button></div><p v-if="taskError" id="reminder-error" class="reminder-error" role="alert">{{ taskError }}</p><p class="reminder-note">提醒仅保存在当前浏览器，按账号和日期分别记录，不会自动发送通知。</p></form>
      <p v-if="!reminders.length" class="home-panel-empty">今天还没有提醒，可以先添加一件想完成的小事。</p>
      <div class="todo-list"><div v-for="r in reminders" :key="r.id" class="todo" :class="{done:r.done}"><button class="todo-check" :aria-label="`${r.done ? '恢复待办' : '标记完成'}：${r.title}`" :aria-pressed="r.done" @click="toggle(r.id)"><AppIcon name="check" :size="12"/></button><div class="todo-main"><b>{{ r.title }}</b><span v-if="'sub' in r">{{ r.sub }}</span></div><span class="todo-time">{{ r.time }}</span></div></div>
    </section>
    <section class="card" aria-labelledby="recent-heading"><div class="card-head"><b id="recent-heading">最近对话</b><span class="sub">当前账号</span></div><div class="recent-list" :aria-busy="recentLoading"><p v-if="recentLoading" class="home-panel-empty" role="status">正在加载最近对话…</p><p v-else-if="!personalRecent.length && !recentError" class="home-panel-empty">还没有对话，选择上方智能体开始咨询吧。</p><p v-if="recentError" class="home-panel-empty" role="status">部分对话暂时无法加载，请稍后刷新重试。</p><RouterLink v-for="r in personalRecent" :key="r.agentId+r.id" class="recent" :to="`/agent/${r.agentId}`" @click="openConversation(r)"><span class="recent-ico" :style="{'--tint':agent(r.agentId).tint,'--c':agent(r.agentId).color}"><AppIcon :name="agent(r.agentId).icon" :size="15"/></span><div class="recent-main"><b>{{ r.title }}</b><span>{{ agent(r.agentId).name }} · {{ displayTime(r.updated_at) }}</span></div><span class="badge">会话</span></RouterLink></div></section>
  </div>
</div></template>
<style scoped>
.reminder-form { padding: 16px 20px 0; display: grid; gap: 8px; }
.reminder-form label { font-size: 14px; color: var(--ink-2); }
.reminder-controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.reminder-controls input { width: auto; flex: 1; min-width: 110px; }
.reminder-controls button, .reminder-form input { min-height: 44px; }
.reminder-note, .home-panel-empty { font-size: 14px; color: var(--ink-2); line-height: 1.7; }
.reminder-note { margin: 4px 0 0; }
.home-panel-empty { padding: 20px; margin: 0; }
.reminder-error { color: var(--brand-ink); margin: 0; font-size: 14px; }
.todo-check { min-width: 44px; min-height: 44px; }
</style>
