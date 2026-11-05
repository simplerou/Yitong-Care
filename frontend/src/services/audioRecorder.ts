import type { Recording } from './voiceInput'

export function canRecord(){return typeof window!=='undefined'&&!!navigator.mediaDevices?.getUserMedia&&typeof MediaRecorder!=='undefined'&&typeof AudioContext!=='undefined'&&typeof OfflineAudioContext!=='undefined'}
export async function openRecording():Promise<Recording>{
  const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false})
  let recorder:MediaRecorder
  try{
    const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus','audio/webm'].find(type=>MediaRecorder.isTypeSupported(type))
    recorder=mime?new MediaRecorder(stream,{mimeType:mime}):new MediaRecorder(stream)
  }catch(error){stream.getTracks().forEach(t=>t.stop());throw error}
  let canceled=false,settled=false,chunks:Blob[]=[],size=0
  let resolve!:(value:Blob|null)=>void,reject!:(error:Error)=>void
  const finished=new Promise<Blob|null>((ok,fail)=>{resolve=ok;reject=fail})
  // A device can fail before the caller attaches its await handler.
  void finished.catch(()=>{})
  const release=()=>{stream.getTracks().forEach(t=>{t.onended=null;t.stop()})}
  function cancel(){
    canceled=true;chunks=[]
    recorder.ondataavailable=null;recorder.onstop=null;recorder.onerror=null
    try{if(recorder.state!=='inactive')recorder.stop()}catch{/* recorder already stopped */}finally{release();if(!settled){settled=true;resolve(null)}}
  }
  recorder.ondataavailable=event=>{
    if(canceled||!event.data.size)return
    size+=event.data.size
    if(size>8_000_000){if(!settled){settled=true;reject(new Error('录音文件过大，请缩短问题。'))}cancel();return}
    chunks.push(event.data)
  }
  recorder.onerror=()=>{if(!settled){settled=true;reject(new Error('录音设备发生错误，请重试。'))}cancel()}
  recorder.onstop=()=>{
    release();recorder.ondataavailable=null;recorder.onerror=null;recorder.onstop=null
    if(settled)return
    settled=true
    const audio=new Blob(chunks,{type:recorder.mimeType||chunks[0]?.type});chunks=[]
    if(canceled)resolve(null)
    else if(!audio.size)reject(new Error('录音为空，请重新录制。'))
    else resolve(audio)
  }
  const stop=()=>{if(recorder.state!=='inactive')recorder.stop()}
  stream.getTracks().forEach(t=>{t.onended=stop})
  try{recorder.start(1000)}catch(error){cancel();throw error}
  return {finished,stop,cancel}
}

export function encodeWav(samples:Float32Array,sampleRate=16000):Blob{
  const data=new ArrayBuffer(44+samples.length*2),view=new DataView(data)
  function ascii(offset:number,value:string){for(let i=0;i<value.length;i++)view.setUint8(offset+i,value.charCodeAt(i))}
  ascii(0,'RIFF');view.setUint32(4,36+samples.length*2,true);ascii(8,'WAVE');ascii(12,'fmt ')
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,sampleRate,true)
  view.setUint32(28,sampleRate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);ascii(36,'data');view.setUint32(40,samples.length*2,true)
  for(let i=0;i<samples.length;i++){const value=Math.max(-1,Math.min(1,samples[i]));view.setInt16(44+i*2,value<0?value*0x8000:value*0x7fff,true)}
  return new Blob([data],{type:'audio/wav'})
}
export async function prepareWav(audio:Blob,signal:AbortSignal):Promise<Blob>{
  signal.throwIfAborted()
  if(audio.size>8_000_000)throw new Error('录音过大，请缩短问题后重试。')
  const context=new AudioContext()
  try{
    const decoded=await context.decodeAudioData(await audio.arrayBuffer())
    signal.throwIfAborted()
    if(decoded.duration<0.2)throw new Error('录音太短，请说完问题再结束。')
    if(decoded.duration>65)throw new Error('录音过长，请将每次问题控制在一分钟以内。')
    const offline=new OfflineAudioContext(1,Math.ceil(decoded.duration*16000),16000)
    const source=offline.createBufferSource();source.buffer=decoded;source.connect(offline.destination);source.start()
    const mono=await offline.startRendering();signal.throwIfAborted()
    return encodeWav(mono.getChannelData(0))
  }catch(error){
    if(signal.aborted)throw error
    if(error instanceof Error&&error.name==='EncodingError')throw new Error('浏览器无法解码本次录音，请重新录制或更换浏览器。')
    throw error
  }finally{await context.close().catch(()=>{})}
}
