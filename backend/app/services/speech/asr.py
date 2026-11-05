"""Qwen-Audio-ASR DashScope HTTP adapter. Audio/text never logged or persisted."""
import base64
import io
import struct
import wave
from urllib.parse import urlsplit
import httpx
from app.core.config import get_settings
from app.core.exceptions import BusinessError

MAX_SECONDS=65
MAX_BYTES=2_100_000

def validate_wav(data):
    if not data:raise BusinessError('录音为空，请重新录制。',422)
    if len(data)>MAX_BYTES:raise BusinessError('录音文件过大，请缩短到一分钟以内。',413)
    try:
        with wave.open(io.BytesIO(data),'rb') as audio:
            if audio.getnchannels()!=1 or audio.getsampwidth()!=2 or audio.getframerate()!=16000 or audio.getcomptype()!='NONE':
                raise BusinessError('请上传16kHz、单声道、16位PCM的WAV录音。',422)
            frames=audio.getnframes()
            duration=frames/16000
            if duration<0.2:raise BusinessError('录音太短，请说完问题后再结束录音。',422)
            if duration>MAX_SECONDS:raise BusinessError('录音过长，请将每次提问控制在一分钟以内。',413)
            if len(audio.readframes(frames))!=frames*2:raise ValueError('incomplete WAV')
    except BusinessError:raise
    except (wave.Error,EOFError,ValueError,struct.error):raise BusinessError('录音格式损坏或不支持，请重新录制。',422) from None
    return duration

class ASRClient:
    def __init__(self,settings=None,transport=None):self.settings=settings or get_settings();self.transport=transport
    def ensure_configured(self):
        s=self.settings
        try:url=urlsplit(s.asr_api_url)
        except ValueError:raise BusinessError('ASR_API_URL 格式不正确，请填写完整 HTTPS 接口地址。',503) from None
        if not s.asr_api_key.get_secret_value().strip() or not s.asr_model.strip():
            raise BusinessError('语音识别模型尚未配置，请在后端填写 ASR_API_KEY。',503)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or '{' in url.netloc:
            raise BusinessError('ASR_API_URL 应为服务商提供的完整 HTTPS 音频识别接口地址。',503)
    def configuration(self):
        try:self.ensure_configured();configured=True
        except BusinessError:configured=False
        return {'configured':configured,'model':self.settings.asr_model,'recording_seconds':60,'max_bytes':MAX_BYTES}
    async def transcribe(self,data):
        self.ensure_configured();duration=validate_wav(data)
        payload={'model':self.settings.asr_model,'input':{'messages':[{'role':'user','content':[{'type':'input_audio','input_audio':{'data':'data:audio/wav;base64,'+base64.b64encode(data).decode()}}]}]},'parameters':{'format':'wav','sample_rate':'16000','language_hints':['zh']}}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.settings.asr_timeout_seconds,connect=10),follow_redirects=False,transport=self.transport) as client:
                response=await client.post(self.settings.asr_api_url,headers={'Authorization':'Bearer '+self.settings.asr_api_key.get_secret_value(),'Content-Type':'application/json','X-DashScope-SSE':'disable'},json=payload)
                if response.status_code!=200:
                    messages={401:'语音模型鉴权失败，请检查 ASR_API_KEY 与服务地址是否匹配。',403:'当前 API Key 无权调用语音模型，请检查服务权限。',429:'语音识别请求过多或额度不足，请稍后重试。'}
                    raise BusinessError(messages.get(response.status_code,f'语音识别服务返回 HTTP {response.status_code}，请检查模型、接口和服务状态。'),502)
                if len(response.content)>200_000:raise ValueError('oversized response')
                raw=response.json()
                if not isinstance(raw,dict) or raw.get('code'):raise ValueError('invalid response')
                output=raw.get('output')
                if not isinstance(output,dict):raise ValueError('missing DashScope output')
                text=output.get('text')
                if text is None and isinstance(output.get('sentence'),dict):text=output['sentence'].get('text')
                if not isinstance(text,str) or len(text)>10000:raise ValueError('invalid transcription')
                text=text.strip()
                if not text:raise BusinessError('没有识别到文字，请靠近麦克风重新录音。',422)
                return {'text':text,'model':self.settings.asr_model,'audio_seconds':round(duration,2)}
        except httpx.TimeoutException:raise BusinessError('语音模型转写超时，请重试或缩短录音。',504) from None
        except httpx.HTTPError:raise BusinessError('无法连接语音识别服务，请检查网络和 ASR_API_URL。',502) from None
        except (ValueError,KeyError,TypeError):raise BusinessError('语音模型返回格式异常，请确认服务支持 DashScope 音频识别协议。',502) from None

def get_asr():return ASRClient()
