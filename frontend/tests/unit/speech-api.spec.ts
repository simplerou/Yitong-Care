import { afterEach,expect,it,vi } from 'vitest'
import { speechApi } from '../../src/api/speech'
afterEach(()=>vi.unstubAllGlobals())
it('上传WAV保持二进制Content-Type和登录凭证，不将音频当JSON',async()=>{
  vi.stubGlobal('sessionStorage',{getItem:()=> 'SESSION_TOKEN'})
  const fetcher=vi.fn(async()=>new Response(JSON.stringify({text:'补贴如何申请',model:'asr',audio_seconds:1}),{status:200,headers:{'Content-Type':'application/json'}}))
  vi.stubGlobal('fetch',fetcher)
  const blob=new Blob(['wav'],{type:'audio/wav'}),controller=new AbortController()
  await speechApi.transcribe(blob,controller.signal)
  const [,options]=fetcher.mock.calls[0] as unknown as [string,RequestInit]
  const headers=new Headers(options.headers)
  expect(headers.get('Content-Type')).toBe('audio/wav')
  expect(headers.get('Authorization')).toBe('Bearer SESSION_TOKEN')
  expect(options.body).toBe(blob)
})
it('已取消的语音请求携带中止信号',async()=>{
  vi.stubGlobal('sessionStorage',{getItem:()=> null})
  vi.stubGlobal('fetch',vi.fn(async(_url,options:RequestInit)=>{expect(options.signal?.aborted).toBe(true);throw new DOMException('aborted','AbortError')}))
  const controller=new AbortController();controller.abort()
  await expect(speechApi.transcribe(new Blob(['wav']),controller.signal)).rejects.toThrow('取消或超时')
})
