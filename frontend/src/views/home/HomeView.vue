<script setup lang="ts">
import { computed } from 'vue'
import { agents } from '../../config/agents'
import { useDemoStore } from '../../stores/demo'
const store = useDemoStore(), s = store.state
const now = new Date(), h = now.getHours(), greet = h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 13 ? '中午好' : h < 18 ? '下午好' : '晚上好'
const date = `${now.getFullYear()}年${now.getMonth()+1}月${now.getDate()}日 星期${'日一二三四五六'[now.getDay()]}`
const stats = computed(() => [
  { icon:'book', label:'知识文档', value:s.docs.length, unit:'份', tint:'#EEF4FF', color:'#1B64F2' },
  { icon:'layers', label:'文本块', value:s.chunks.length, unit:'段', tint:'#F0EDFB', color:'#6E56CF' },
  { icon:'database', label:'向量条目', value:store.vectorCount, unit:'条', tint:'#E7F8F0', color:'#0FA968' },
  { icon:'message', label:'今日问答', value:52 + Object.values(s.chats).reduce((n,m) => n + m.filter(x => x.role === 'user').length,0) + s.history.length, unit:'次', tint:'#FDF3E0', color:'#E8930C' }
])
const pipeline = computed(() => [
  {title:'文档上传',desc:'PDF / Word / TXT',to:'/kb',stat:`${s.docs.length} 份文档`,icon:'upload'},
  {title:'文本切块',desc:'按句切分 + 重叠',to:'/chunk',stat:`${s.chunks.length} 个文本块`,icon:'scissors'},
  {title:'向量入库',desc:'Embedding + 索引',to:'/vector',stat:`${store.vectorCount} 条向量`,icon:'database'},
  {title:'向量检索',desc:'余弦相似度 TopK',to:'/search',stat:'TopK 5 · 阈值 0.12',icon:'search'},
  {title:'结果与原文',desc:'片段展示 + 出处',to:'/records',stat:`${s.history.length} 次检索记录`,icon:'history'}
])
const recent = computed(() => {
  const rows = Object.entries(s.chats).flatMap(([agentId,messages]) => { const user = messages.find(m => m.role === 'user'); return user ? [{agentId,q:user.text,time:user.time,demo:false}] : [] })
  return [...rows, ...store.services.filter(r => r.demo)].slice(0,4)
})
const agent = (id: string) => agents.find(a => a.id === id) || agents[0]
function toggle(id: string) { const r = s.reminders.find(r => r.id === id); if (r) { r.done = !r.done; store.notify(r.done ? '已标记完成' : '已恢复为待办') } }
</script>
<template><div class="page" style="--tint:#EEF4FF;--c:#1B64F2">
  <div class="hero"><div class="hero-main"><div class="hero-eyebrow"><span class="pin"></span>杭州市 · 拱墅区 · 和睦社区养老服务中心</div><h1>{{ greet }}，张阿姨</h1><p>今天是 {{ date }}。您还有 {{ store.pendingCount }} 项健康任务待完成。想了解政策、调理饮食或身体不舒服，都可以直接问智能体。</p><div class="hero-actions"><RouterLink class="btn light lg" to="/agent/health"><AppIcon name="message" :size="16"/> 开始健康咨询</RouterLink><button class="btn glass lg" @click="store.toggleSenior"><AppIcon name="sparkles" :size="16"/> {{ store.senior ? '退出长辈模式' : '长辈模式' }}</button></div></div><div class="hero-side"><div class="score-ring" style="--p:86"><span>86<small>健康分</small></span></div><div class="hero-note"><div class="hn-row"><span>今日守护</span><b>{{ store.pendingCount }} 项待办</b></div><ul><li :class="{done:s.reminders[0].done}"><i></i>晨起降压药已服用</li><li :class="{done:s.reminders[1].done}"><i></i>血压待记录</li><li :class="{done:s.reminders[2].done}"><i></i>助餐已预订</li></ul></div></div></div>
  <div class="stat-row"><div v-for="stat in stats" :key="stat.label" class="stat"><span class="stat-ico" :style="{'--tint':stat.tint,'--c':stat.color}"><AppIcon :name="stat.icon" :size="19"/></span><div><div class="stat-val">{{ stat.value.toLocaleString('zh-CN') }}<small>{{ stat.unit }}</small></div><div class="stat-label">{{ stat.label }}</div></div></div></div>
  <div class="sec-head"><div class="sec-title">智能体服务</div><RouterLink class="sec-link" to="/services">服务记录 <AppIcon name="right" :size="12"/></RouterLink></div><div class="svc-grid"><RouterLink v-for="a in agents" :key="a.id" class="svc" :to="`/agent/${a.id}`" :style="{'--tint':a.tint,'--c':a.color}"><span class="svc-ico"><AppIcon :name="a.icon" :size="21"/></span><span class="svc-body"><b>{{ a.name }}</b><p>{{ a.desc }}</p><span class="svc-tag"><AppIcon name="database" :size="10"/> 已接入 {{ a.kbNames.length }} 个知识库</span></span></RouterLink></div>
  <div class="sec-head"><div class="sec-title">知识库与 RAG 全链路</div><span class="sec-link">文档 → 切块 → 向量 → 检索 → 原文</span></div><div class="pipeline"><RouterLink v-for="(p,i) in pipeline" :key="p.to" class="pipe" :to="p.to"><div class="pipe-top"><span class="pipe-num">{{ i+1 }}</span><AppIcon :name="p.icon" :size="15"/></div><h4>{{ p.title }}</h4><p>{{ p.desc }}</p><div class="pipe-stat">{{ p.stat }}</div></RouterLink></div>
  <div class="bottom-grid"><div class="card"><div class="card-head"><b>今日守护</b><span class="sub">{{ store.pendingCount }} 项待完成</span></div><div class="todo-list"><div v-for="r in s.reminders" :key="r.id" class="todo" :class="{done:r.done}"><button class="todo-check" :aria-label="`${r.done ? '恢复待办' : '标记完成'}：${r.title}`" :aria-pressed="r.done" @click="toggle(r.id)"><AppIcon name="check" :size="12"/></button><div class="todo-main"><b>{{ r.title }}</b><span>{{ r.sub }}</span></div><span class="todo-time">{{ r.time }}</span></div></div></div><div class="card"><div class="card-head"><b>最近对话</b><RouterLink class="sub" to="/services" style="color:#1b64f2">查看全部</RouterLink></div><div class="recent-list"><RouterLink v-for="(r,i) in recent" :key="i" class="recent" :to="`/agent/${r.agentId}`"><span class="recent-ico" :style="{'--tint':agent(r.agentId).tint,'--c':agent(r.agentId).color}"><AppIcon :name="agent(r.agentId).icon" :size="15"/></span><div class="recent-main"><b>{{ r.q }}</b><span>{{ agent(r.agentId).name }} · {{ r.time }}</span></div><span class="badge" :class="{green:!r.demo}">{{ r.demo ? '示例' : '已回复' }}</span></RouterLink></div></div></div>
</div></template>
