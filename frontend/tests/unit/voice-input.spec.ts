import { afterEach,beforeEach,expect,it,vi } from 'vitest'
import { appendVoiceText,createVoiceInput,type Recording,type VoiceState } from '../../src/services/voiceInput'
import { encodeWav } from '../../src/services/audioRecorder'
beforeEach(()=>vi.useFakeTimers())
afterEach(()=>{vi.clearAllTimers();vi.useRealTimers()})
function setup(){
  let resolve!:(audio:Blob|null)=>void
  const finished=new Promise<Blob|null>(ok=>{resolve=ok})
  const recording:Recording={finished,stop:vi.fn(()=>resolve(new Blob(['audio']))),cancel:vi.fn(()=>resolve(null))}
  const states:VoiceState[]=[],finals:string[]=[],transcribe=vi.fn(async(_audio:Blob,_signal:AbortSignal)=>'杭州的养老补贴有哪些？')
  const voice=createVoiceInput({open:async()=>recording,transcribe,onState:s=>states.push(s),onFinal:t=>finals.push(t)})
  return {voice,recording,states,finals,transcribe,resolve}
}
it('录音结束才调用模型，结果填入而不自动发送',async()=>{
  const {voice,states,transcribe,finals}=setup()
  const running=voice.start();await Promise.resolve()
  expect(states.at(-1)?.phase).toBe('listening');expect(transcribe).not.toHaveBeenCalled()
  voice.stop();await running
  expect(transcribe).toHaveBeenCalledOnce();expect(finals).toEqual(['杭州的养老补贴有哪些？'])
  expect(states.some(s=>s.phase==='transcribing')).toBe(true)
  expect(states.at(-1)?.phase).toBe('idle');expect(vi.getTimerCount()).toBe(0)
})
it('会话切换取消录音，不提交音频',async()=>{
  const {voice,recording,transcribe,finals}=setup();const running=voice.start();await Promise.resolve();voice.cancel();await running
  expect(recording.cancel).toHaveBeenCalledOnce();expect(transcribe).not.toHaveBeenCalled();expect(finals).toEqual([])
})
it('取消转写时中止请求，并屏蔽迟到的模型结果',async()=>{
  const s=setup();let finish!:(text:string)=>void,signal:AbortSignal|undefined
  s.transcribe.mockImplementation((_audio,sig)=>{signal=sig;return new Promise<string>(ok=>{finish=ok})})
  const running=s.voice.start();await Promise.resolve();s.voice.stop();await Promise.resolve()
  expect(s.states.at(-1)?.phase).toBe('transcribing');s.voice.cancel();expect(signal?.aborted).toBe(true)
  finish('迟到的结果');await running;expect(s.finals).toEqual([])
})
it('等待麦克风许可时取消，后取得的麦克风也会释放',async()=>{
  let permit!:(recording:Recording)=>void
  const s=setup(),voice=createVoiceInput({open:()=>new Promise(ok=>{permit=ok}),transcribe:s.transcribe,onState:vi.fn(),onFinal:vi.fn()})
  const running=voice.start();voice.cancel();permit(s.recording);await running
  expect(s.recording.cancel).toHaveBeenCalledOnce();expect(s.transcribe).not.toHaveBeenCalled()
})
it('权限拒绝、模型失败时恢复文字输入',async()=>{
  const states:VoiceState[]=[]
  const denied=createVoiceInput({open:async()=>{throw new DOMException('denied','NotAllowedError')},transcribe:vi.fn(),onState:s=>states.push(s),onFinal:vi.fn()})
  await denied.start();expect(states.at(-1)?.message).toContain('权限')
  const s=setup();s.transcribe.mockRejectedValue(new Error('语音模型转写超时'))
  const running=s.voice.start();await Promise.resolve();s.voice.stop();await running
  expect(s.states.at(-1)?.phase).toBe('error');expect(s.states.at(-1)?.message).toContain('超时');expect(s.finals).toEqual([])
})
it('60秒自动结束录音并提交转写',async()=>{
  const s=setup();const running=s.voice.start();await Promise.resolve();vi.advanceTimersByTime(60_000);await running
  expect(s.recording.stop).toHaveBeenCalledOnce();expect(s.transcribe).toHaveBeenCalledOnce()
})
it('录音结束没有回调时超时释放麦克风',async()=>{
  const s=setup();vi.mocked(s.recording.stop).mockImplementation(()=>{})
  const running=s.voice.start();await Promise.resolve();s.voice.stop();vi.advanceTimersByTime(3000);await running
  expect(s.recording.cancel).toHaveBeenCalledOnce();expect(s.states.at(-1)?.phase).toBe('error');expect(s.transcribe).not.toHaveBeenCalled()
})
it('原有文字保留并限制1000字',()=>{
  expect(appendVoiceText('杭州户籍','我想问补贴')).toBe('杭州户籍 我想问补贴')
  expect(appendVoiceText('杭州户籍 ','补贴')).toBe('杭州户籍 补贴')
  expect(appendVoiceText('原文','')).toBe('原文')
  expect(appendVoiceText('甲'.repeat(998),'乙'.repeat(10))).toHaveLength(1000)
})
it('输出真实16kHz单声道PCM16 WAV，采样值饱和裁剪',async()=>{
  const wav=encodeWav(new Float32Array([-2,0,2])),view=new DataView(await wav.arrayBuffer())
  expect(wav.type).toBe('audio/wav');expect(wav.size).toBe(50)
  expect(view.getUint16(22,true)).toBe(1);expect(view.getUint32(24,true)).toBe(16000)
  expect(view.getUint16(34,true)).toBe(16)
  expect(view.getInt16(44,true)).toBe(-32768);expect(view.getInt16(48,true)).toBe(32767)
})
