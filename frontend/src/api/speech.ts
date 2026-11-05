import { request } from './http'
export interface SpeechConfig {configured:boolean;model:string;recording_seconds:number;max_bytes:number}
export const speechApi={
  config:()=>request<SpeechConfig>('/speech/config'),
  transcribe:(wav:Blob,signal:AbortSignal)=>request<{text:string;model:string;audio_seconds:number}>('/speech/transcribe',{method:'POST',body:wav,headers:{'Content-Type':'audio/wav'},signal},195_000),
}
