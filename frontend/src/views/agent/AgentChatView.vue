<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { agents } from '../../config/agents'
import { useDemoStore } from '../../stores/demo'
import { useOverlay } from '../../composables/useOverlay'
import AppBreadcrumb from '../../components/layout/AppBreadcrumb.vue'
import ChatMessage from '../../components/chat/ChatMessage.vue'
import ChatComposer from '../../components/chat/ChatComposer.vue'
import SourcePanel from '../../components/chat/SourcePanel.vue'
const props=defineProps<{id:string}>(), store=useDemoStore(), ui=useOverlay(), body=ref<HTMLElement>()
const agent=computed(()=>agents.find(a=>a.id===props.id) || agents[0])
watch(agent,a=>store.ensureChat(a),{immediate:true})
const messages=computed(()=>store.state.chats[agent.value.id] || [])
const vectorCount=computed(()=>store.state.chunks.filter(c=>agent.value.kbIds.includes(c.docId)&&c.vectorized).length)
watch(()=>messages.value.map(m=>m.text+m.status).join(''),async()=>{await nextTick();if(body.value)body.value.scrollTop=body.value.scrollHeight})
function send(q:string) {void store.ask(agent.value,q)}
function regenerate() {const last=[...messages.value].reverse().find(m=>m.role==='user');if(last)void store.ask(agent.value,last.text,true)}
function clear() {ui.confirm('清空对话',`将清空与「${agent.value.name}」的全部对话记录（不影响知识库与检索记录）。`,()=>store.clearChat(agent.value),'清空')}
</script>
<template><div class="page"><AppBreadcrumb/><div class="card agent-head" :style="{'--tint':agent.tint,'--c':agent.color}"><span class="agent-ico"><AppIcon :name="agent.icon" :size="26"/></span><div class="agent-id"><h1>{{ agent.name }} <span class="badge green live">演示</span></h1><p>{{ agent.role }} · 已接入 {{ agent.kbNames.length }} 个知识库 · 答案附带原文出处</p></div><div class="agent-kbs"><span v-for="name in agent.kbNames" :key="name" class="badge blue"><AppIcon name="book" :size="10"/> {{ name }}</span></div><div class="agent-actions"><button class="btn sm" :disabled="store.state.busy" @click="clear"><AppIcon name="refresh" :size="13"/> 清空对话</button><button class="btn sm" @click="ui.open({kind:'human',title:'转人工服务',subtitle:'社区养老顾问会尽快与您联系',desc:agent.name})"><AppIcon name="message" :size="13"/> 转人工</button></div></div><div class="agent-layout"><section class="card chat-panel"><div class="chat-head"><b>对话</b><span class="badge violet">RAG 增强</span><div class="chat-head-right"><span class="model-chip"><i></i>Qwen 待接入 · 当前演示</span><span>{{ vectorCount }} 条可检索向量</span></div></div><div id="chatBody" ref="body" class="chat-body"><ChatMessage v-for="(message,i) in messages" :key="`${agent.id}-${i}`" :agent="agent" :message="message" :data-mi="i" @suggest="send" @regenerate="regenerate"/></div><ChatComposer :busy="store.state.busy" @send="send"/></section><SourcePanel :agent="agent"/></div></div></template>
