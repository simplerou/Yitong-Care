<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { currentAccount, isResident } from '../../api/auth'
import { speechApi, type SpeechConfig } from '../../api/speech'
import { canRecord, openRecording, prepareWav } from '../../services/audioRecorder'
import { appendVoiceText, createVoiceInput, type VoiceState } from '../../services/voiceInput'
const props=defineProps<{busy:boolean;placeholder?:string;contextKey?:string}>(),emit=defineEmits<{send:[text:string]}>(),text=ref('')
const supported=ref(false),secure=ref(true),config=ref<SpeechConfig|null>(null),configError=ref('')
const voiceState=ref<VoiceState>({phase:'idle',message:''})
const active=computed(()=>['starting','listening','stopping','transcribing'].includes(voiceState.value.phase))
let original='',limited=false
const voice=createVoiceInput({
  open:openRecording,
  transcribe:async(audio,signal)=>{const wav=await prepareWav(audio,signal);return (await speechApi.transcribe(wav,signal)).text},
  onState:state=>{voiceState.value=state;if(limited&&state.phase==='idle')voiceState.value.message='已达到1000字上限，超出的文字未填入，请检查并精简后发送。'},
  onFinal:transcript=>{const joined=original+(original&&transcript&&!/\s$/.test(original)?' ':'')+transcript;limited=joined.length>1000;text.value=appendVoiceText(original,transcript)},
})
function cancelVoice(){limited=false;voice.cancel()}
function send(){if(props.busy||active.value||!text.value.trim())return;emit('send',text.value);text.value='';cancelVoice()}
function key(event:KeyboardEvent){if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();send()}}
function toggleVoice(){
  if(active.value){voice.stop();return}
  if(props.busy||!isResident.value||!supported.value||!secure.value||!config.value?.configured)return
  original=text.value;limited=false;void voice.start()
}
async function loadConfig(){try{config.value=await speechApi.config();configError.value=''}catch(error){configError.value=error instanceof Error?error.message:'语音配置读取失败'}}
function hidden(){if(document.hidden)cancelVoice()}
onMounted(()=>{supported.value=canRecord();secure.value=window.isSecureContext;if(isResident.value)void loadConfig();document.addEventListener('visibilitychange',hidden)})
onBeforeUnmount(()=>{voice.dispose();document.removeEventListener('visibilitychange',hidden)})
watch(()=>props.busy,value=>{if(value)cancelVoice()})
watch(isResident,value=>{if(!value)cancelVoice();else void loadConfig()})
watch(()=>currentAccount.value?.id,()=>{cancelVoice();text.value=''})
watch(()=>props.contextKey,()=>{cancelVoice();text.value=''})
const buttonLabel=computed(()=>voiceState.value.phase==='starting'?'取消开启':voiceState.value.phase==='transcribing'?'取消转写':voiceState.value.phase==='stopping'?'正在结束…':active.value?'结束录音':'语音输入')
const voiceHelp=computed(()=>!secure.value?'录音需要 HTTPS 或本机 localhost，请先使用键盘输入。':!supported.value?'当前浏览器不支持录音，请使用新版浏览器或键盘输入。':configError.value||(!config.value?'正在读取语音模型配置…':!config.value.configured?'语音模型尚未配置，请联系管理员填写 ASR_API_KEY。':voiceState.value.message||'点击“语音输入”录音，说完结束，模型识别后可修改文字再发送。'))
</script>
<template><div class="composer" :class="{'resident-composer':isResident}"><div class="composer-box">
<textarea id="chatInput" v-model="text" rows="1" aria-label="描述您的问题" :readonly="active" :aria-describedby="isResident?'voice-help':undefined" :placeholder="placeholder || '请描述您的问题，例如：最近血压有点高，饮食上要注意什么？'" maxlength="1000" :style="{height:Math.min(110,Math.max(38, text.split('\n').length*22+16))+'px'}" @keydown="key"></textarea>

<div class="composer-foot"><span class="composer-hint">{{ isResident?'请核对问题后发送':'Enter 发送 · Shift + Enter 换行 · 回答可核对原文' }}</span><div class="composer-actions">
<button v-if="isResident" type="button" class="voice-input-btn" :class="{listening:active}" :aria-pressed="active" :disabled="busy||!supported||!secure||!config?.configured||voiceState.phase==='stopping'||(!active&&text.length>=1000)" @click="toggleVoice"><AppIcon :name="active?'stop':'mic'" :size="21"/><span>{{ buttonLabel }}</span></button>
<button id="sendBtn" type="button" class="send-btn" :disabled="busy||active||!text.trim()" title="发送" aria-label="发送问题" @click="send"><AppIcon name="send" :size="18"/><span v-if="isResident">发送</span></button>
</div></div></div><p v-if="isResident" id="voice-help" class="voice-help" :class="{'voice-error':voiceState.phase==='error'}" role="status" aria-live="polite">{{ voiceHelp }}</p><button v-if="isResident&&configError" type="button" class="link-btn" @click="loadConfig">重新读取语音配置</button><p v-if="isResident&&supported&&secure" class="voice-privacy">结束录音后将音频提交至配置的语音模型服务识别；请勿说出不必要的隐私信息。</p></div></template>
<style scoped>
.composer-actions{display:flex;align-items:center;gap:10px;flex-shrink:0}.voice-input-btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:48px;padding:10px 16px;border:1px solid var(--brand-100);border-radius:12px;background:var(--brand-50);color:var(--brand-ink);font-size:16px;font-weight:600;cursor:pointer}.voice-input-btn.listening{background:var(--red-50);color:#9e2831;border-color:#f0b8bc}.voice-input-btn:disabled{opacity:.6;cursor:not-allowed}.voice-help,.voice-privacy{margin:9px 0 0;font-size:14px;line-height:1.65;color:var(--ink-2)}.voice-privacy{font-size:12px;color:var(--muted)}.voice-error{color:#9e2831}.voice-interim{margin-top:8px;padding:10px 12px;background:var(--brand-50);border-radius:8px;font-size:16px;line-height:1.7;overflow-wrap:anywhere;color:var(--ink-2)}.voice-interim span{font-weight:600}.resident-composer .composer-foot{gap:10px;flex-wrap:wrap}.resident-composer textarea{font-size:18px;min-height:56px}.resident-composer .composer-hint{font-size:14px}.resident-composer .send-btn{display:inline-flex;gap:7px;width:auto;min-width:88px;height:48px;padding:0 14px;font-size:16px}.composer-actions button:focus-visible{outline:3px solid var(--brand);outline-offset:3px}@media(max-width:480px){.resident-composer .composer-actions{width:100%}.voice-input-btn{flex:1}.resident-composer .send-btn{flex:1}.voice-help{font-size:14px}}
</style>
