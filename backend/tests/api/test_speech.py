import io
import json
import wave
import base64
import pytest
import httpx
from sqlalchemy import select
from app.models.auth import Account
from app.core.config import Settings
from app.core.exceptions import BusinessError
from app.services.speech.asr import ASRClient,get_asr,validate_wav,MAX_BYTES


def wav(seconds=1,rate=16000):
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(rate);audio.writeframes(b'\x01\x00'*int(rate*seconds))
    return buffer.getvalue()

def settings(**kwargs):return Settings(_env_file=None,asr_api_key='SECRET_TEST_KEY',**kwargs)

@pytest.fixture
def speech(client):
    api,_,factory=client
    with factory() as db:
        db.scalar(select(Account).where(Account.phone=='13800000000')).role='resident';db.commit()
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'output':{'text':'杭州市养老补贴有哪些？'}})
    api.app.dependency_overrides[get_asr]=lambda:ASRClient(settings(),httpx.MockTransport(handler))
    return api,calls


def test_audio_transcribes_native_payload_and_keeps_key_server_side(speech):
    api,calls=speech
    audio=wav();response=api.post('/api/speech/transcribe',content=audio,headers={'Content-Type':'audio/wav'})
    assert response.status_code==200,response.text
    assert response.json()['text']=='杭州市养老补贴有哪些？'
    assert response.headers['cache-control']=='no-store'
    payload=json.loads(calls[0].content)
    assert payload['model']=='qwen-audio-3.0-asr-flash'
    assert payload['parameters']['format']=='wav' and payload['parameters']['language_hints']==['zh']
    encoded=payload['input']['messages'][0]['content'][0]['input_audio']['data']
    assert base64.b64decode(encoded.split(',')[1])==audio
    assert calls[0].headers['Authorization']=='Bearer SECRET_TEST_KEY'
    config=api.get('/api/speech/config')
    assert config.json()['configured'] is True
    assert 'SECRET_TEST_KEY' not in response.text+config.text


def test_rejects_invalid_audio_before_provider_call(speech):
    api,calls=speech
    for data,code in [(b'',422),(b'not audio',422),(wav(rate=8000),422),(wav(seconds=.1),422),(b'x'*(MAX_BYTES+1),413)]:
        assert api.post('/api/speech/transcribe',content=data,headers={'Content-Type':'audio/wav'}).status_code==code
    assert api.post('/api/speech/transcribe',content=wav(),headers={'Content-Type':'application/json'}).status_code==415
    assert not calls


def test_only_resident_accounts_can_use_speech(client):
    api,_,_=client
    assert api.get('/api/speech/config').status_code==403
    assert api.post('/api/speech/transcribe',content=wav(),headers={'Content-Type':'audio/wav'}).status_code==403
    api.headers.clear()
    assert api.get('/api/speech/config').status_code==401


def test_missing_key_is_explicit_and_not_sent_upstream(speech):
    api,_=speech
    api.app.dependency_overrides[get_asr]=lambda:ASRClient(Settings(_env_file=None))
    assert api.get('/api/speech/config').json()['configured'] is False
    response=api.post('/api/speech/transcribe',content=wav(),headers={'Content-Type':'audio/wav'})
    assert response.status_code==503 and 'ASR_API_KEY' in response.text


@pytest.mark.parametrize('status,body,expected',[(401,{'message':'SECRET_TEST_KEY'},502),(429,{},502),(200,{'choices':[]},502),(200,{'output':{'text':''}},422)])
def test_upstream_errors_are_sanitized(speech,status,body,expected):
    api,_=speech
    api.app.dependency_overrides[get_asr]=lambda:ASRClient(settings(),httpx.MockTransport(lambda req:httpx.Response(status,json=body)))
    result=api.post('/api/speech/transcribe',content=wav(),headers={'Content-Type':'audio/wav'})
    assert result.status_code==expected and 'SECRET_TEST_KEY' not in result.text


def test_timeout_returns_clear_error(speech):
    api,_=speech
    def timeout(_):raise httpx.ReadTimeout('SECRET_TEST_KEY')
    api.app.dependency_overrides[get_asr]=lambda:ASRClient(settings(),httpx.MockTransport(timeout))
    response=api.post('/api/speech/transcribe',content=wav(),headers={'Content-Type':'audio/wav'})
    assert response.status_code==504 and 'SECRET_TEST_KEY' not in response.text
