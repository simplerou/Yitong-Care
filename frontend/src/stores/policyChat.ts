import { computed,ref } from 'vue'
import { defineStore } from 'pinia'
import { conversationsApi,type StoredTurn,type ConversationRecord,type ConversationDetail } from '../api/chat'
import { ApiError } from '../api/http'
const selectionKey='yitong-policy-conversation'
const message=(e:unknown)=>e instanceof Error?e.message:'会话服务异常，请重试。'
export const usePolicyChatStore=defineStore('policyChat',()=>{
 const sessions=ref<ConversationRecord[]>([]),total=ref(0),page=ref(1),active=ref<ConversationRecord|null>(null),turns=ref<StoredTurn[]>([])
 const loading=ref(false),sending=ref(false),error=ref(''),hasMore=ref(false),before=ref<number|null>(null),evidenceTurnId=ref(''),unconfirmed=ref(false)
 const last=computed(()=>turns.value.at(-1)),pending=computed(()=>last.value?.status==='running'&&!last.value.transient)
 const busy=computed(()=>loading.value||sending.value||pending.value)
 const latest=computed(()=>turns.value.find(t=>t.id===evidenceTurnId.value)?.response||null)
 let generation=0,poll:ReturnType<typeof setTimeout>|undefined,controller:AbortController|undefined
 let uncertain:{id:string;question:string;conversationId:string}|null=null
 function remember(id:string){try{if(id)localStorage.setItem(selectionKey,id);else localStorage.removeItem(selectionKey)}catch{/* Selection storage is optional. */}}
 function savedSelection(){try{return localStorage.getItem(selectionKey)||''}catch{return ''}}
 function apply(detail:ConversationDetail){active.value=detail.conversation;turns.value=detail.turns;hasMore.value=detail.has_more;before.value=detail.next_before_seq;evidenceTurnId.value=[...detail.turns].reverse().find(t=>t.response)?.id||'';remember(detail.conversation.id)}
 function schedule(){clearTimeout(poll);if(!pending.value||!active.value)return;const token=generation,id=active.value.id;poll=setTimeout(async()=>{
  try{const detail=await conversationsApi.detail(id);if(token!==generation)return;apply(detail);error.value=''}
  catch(e){if(token===generation){error.value=message(e);if(e instanceof ApiError&&e.status===404){active.value=null;turns.value=[];evidenceTurnId.value='';remember('');void loadList().catch(()=>{})}}}
  if(token===generation)schedule()
 },3000)}
 async function loadList(append=false){const next=append?page.value+1:1;const token=generation;const data=await conversationsApi.list(next);if(token!==generation)return;page.value=next;total.value=data.total;sessions.value=append?[...sessions.value,...data.items.filter(item=>!sessions.value.some(s=>s.id===item.id))]:data.items}
 async function select(id:string){if(sending.value)return;clearTimeout(poll);const token=++generation;loading.value=true;error.value='';unconfirmed.value=false;uncertain=null
  try{const detail=await conversationsApi.detail(id);if(token!==generation)return;apply(detail);schedule()}
  catch(e){if(token===generation){error.value=message(e);if(e instanceof ApiError&&e.status===404){active.value=null;turns.value=[];evidenceTurnId.value='';remember('')}}}
  finally{if(token===generation)loading.value=false}
 }
 async function initialize(){loading.value=true;error.value='';try{await loadList();const selected=savedSelection()||sessions.value[0]?.id;if(selected){await select(selected);if(!active.value&&sessions.value[0])await select(sessions.value[0].id)}}catch(e){error.value=message(e)}finally{loading.value=false}}
 async function create(){if(busy.value)return;loading.value=true;error.value='';clearTimeout(poll);++generation
  try{const row=await conversationsApi.create();active.value=row;turns.value=[];hasMore.value=false;before.value=null;evidenceTurnId.value='';uncertain=null;unconfirmed.value=false;remember(row.id);await loadList()}
  catch(e){error.value=message(e)}finally{loading.value=false}
 }
 async function older(){if(!active.value||!before.value||loading.value)return;const token=generation;loading.value=true;try{const detail=await conversationsApi.detail(active.value.id,before.value);if(token!==generation)return;turns.value=[...detail.turns.filter(t=>!turns.value.some(old=>old.id===t.id)),...turns.value];hasMore.value=detail.has_more;before.value=detail.next_before_seq}catch(e){if(token===generation)error.value=message(e)}finally{if(token===generation)loading.value=false}}
 function accept(turn:StoredTurn){const index=turns.value.findIndex(t=>t.id===turn.id);if(index>=0)turns.value[index]=turn;else turns.value.push(turn);turns.value.sort((a,b)=>a.seq-b.seq);if(turn.response)evidenceTurnId.value=turn.id;unconfirmed.value=false;uncertain=null}
 async function submit(id:string,question:string,retry:boolean){
  if(!active.value)return;const conversationId=active.value.id,token=generation;sending.value=true;error.value='';evidenceTurnId.value='';controller=new AbortController()
  const now=new Date().toISOString();const prior=turns.value.find(t=>t.id===id)
  if(prior){prior.status='running';prior.error=null}else turns.value.push({id,conversation_id:conversationId,seq:(last.value?.seq||0)+1,question,status:'running',attempts:1,response:null,error:null,created_at:now,updated_at:now,transient:true})
  try{const turn=await conversationsApi.ask(conversationId,id,question,retry,controller.signal);if(token!==generation)return;accept(turn);void loadList().catch(()=>{})}
  catch(e){if(token!==generation)return;error.value=message(e)
   try{const detail=await conversationsApi.detail(conversationId);if(token!==generation)return;apply(detail);const stored=detail.turns.find(t=>t.id===id)
    if(stored){uncertain=null;unconfirmed.value=false;if(stored.status==='succeeded')error.value='';else if(stored.status==='failed')error.value=stored.error||error.value}
    else{uncertain={id,question,conversationId};unconfirmed.value=true;error.value='请求保存状态尚未确认。点击重试将先核对服务器，再使用同一请求标识处理。'}
   }catch{if(token===generation){uncertain={id,question,conversationId};unconfirmed.value=true;const row=turns.value.find(t=>t.id===id);if(row)row.status='failed'}}
  }finally{if(token===generation){sending.value=false;schedule()}}
 }
 async function send(question:string){if(busy.value||unconfirmed.value||!question.trim())return;if(!active.value)await create();if(!active.value)return;await submit(crypto.randomUUID(),question.trim(),false)}
 async function retry(){if(busy.value||!active.value)return
  if(uncertain){const task=uncertain;try{const detail=await conversationsApi.detail(task.conversationId);apply(detail);const turn=detail.turns.find(t=>t.id===task.id)
    if(turn?.status==='succeeded'){uncertain=null;unconfirmed.value=false;error.value='';return}
    if(turn?.status==='running'){uncertain=null;unconfirmed.value=false;schedule();return}
    unconfirmed.value=false;await submit(task.id,task.question,!!turn)
   }catch(e){error.value=message(e)}return}
  if(last.value?.status==='failed')await submit(last.value.id,last.value.question,true);else await initialize()
 }
 async function remove(){if(busy.value||!active.value)return;loading.value=true;error.value='';const id=active.value.id
  try{await conversationsApi.remove(id);remember('');active.value=null;turns.value=[];evidenceTurnId.value='';hasMore.value=false;uncertain=null;unconfirmed.value=false;++generation;await loadList()}
  catch(e){error.value=message(e)}finally{loading.value=false}
  if(!active.value&&sessions.value[0])await select(sessions.value[0].id)
 }
 async function moreSessions(){try{await loadList(true)}catch(e){error.value=message(e)}}
 function stop(){++generation;clearTimeout(poll);controller?.abort();sending.value=false;loading.value=false}
 return{sessions,total,active,turns,loading,sending,error,hasMore,before,evidenceTurnId,unconfirmed,busy,pending,latest,initialize,select,create,older,send,retry,remove,moreSessions,stop}
})
