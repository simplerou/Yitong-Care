/** Recorder lifecycle. Model transcription is injected, never sent as an Agent question. */
export type VoicePhase='idle'|'starting'|'listening'|'stopping'|'transcribing'|'error'
export interface VoiceState {phase:VoicePhase;message:string}
export interface Recording {finished:Promise<Blob|null>;stop():void;cancel():void}
interface Options {open:()=>Promise<Recording>;transcribe:(audio:Blob,signal:AbortSignal)=>Promise<string>;onState:(state:VoiceState)=>void;onFinal:(text:string)=>void;maxDurationMs?:number}
export function createVoiceInput(options:Options){
  let epoch=0,recording:Recording|null=null,request:AbortController|null=null
  let state:VoiceState={phase:'idle',message:''}
  let duration:ReturnType<typeof setTimeout>|undefined,ending:ReturnType<typeof setTimeout>|undefined
  const publish=(update:VoiceState)=>{state=update;options.onState({...state})}
  const clear=()=>{clearTimeout(duration);clearTimeout(ending);duration=ending=undefined}
  function cancel(){epoch++;clear();recording?.cancel();recording=null;request?.abort();request=null;publish({phase:'idle',message:''})}
  function stop(){
    if(state.phase==='starting'||state.phase==='transcribing'){cancel();return}
    if(!recording||state.phase==='stopping')return
    publish({phase:'stopping',message:'正在结束录音…'})
    clearTimeout(duration)
    try{recording.stop()}catch{cancel();publish({phase:'error',message:'无法结束录音，请重试。'});return}
    ending=setTimeout(()=>{cancel();publish({phase:'error',message:'录音结束超时，请重新录制。'})},3000)
  }
  async function start(){
    if(!['idle','error'].includes(state.phase))return
    const id=++epoch
    publish({phase:'starting',message:'正在开启麦克风，请按浏览器提示允许使用。'})
    try{
      const opened=await options.open()
      if(id!==epoch){opened.cancel();return}
      recording=opened
      publish({phase:'listening',message:'正在录音，请说出问题；说完点击“结束录音”。最长60秒。'})
      duration=setTimeout(stop,options.maxDurationMs??60_000)
      const audio=await opened.finished
      if(id!==epoch)return
      clear();recording=null
      if(!audio){publish({phase:'idle',message:'录音已取消。'});return}
      publish({phase:'transcribing',message:'录音已结束，模型正在识别，请稍候…'})
      request=new AbortController()
      const text=await options.transcribe(audio,request.signal)
      if(id!==epoch)return
      request=null
      if(!text.trim())throw new Error('没有识别到文字，请靠近麦克风重试。')
      options.onFinal(text)
      publish({phase:'idle',message:'识别完成，请核对药名、数字和地区，修改后点击发送。'})
    }catch(error){
      if(id!==epoch)return
      clear();recording?.cancel();recording=null;request?.abort();request=null
      const name=error instanceof Error?error.name:''
      const permission=['NotAllowedError','PermissionDeniedError','SecurityError'].includes(name)
      const noDevice=['NotFoundError','NotReadableError','DevicesNotFoundError','TrackStartError'].includes(name)
      publish({phase:'error',message:permission?'麦克风权限未开启，请在浏览器网站设置中允许后重试。':noDevice?'无法使用麦克风，请检查设备连接和占用情况。':error instanceof Error?error.message:'语音识别未完成，请重试或使用键盘输入。'})
    }
  }
  return {start,stop,cancel,dispose:cancel}
}
export function appendVoiceText(original:string,transcript:string,limit=1000){
  const separator=original&&transcript&&!/\s$/.test(original)?' ':''
  return (original+separator+transcript).slice(0,limit)
}
