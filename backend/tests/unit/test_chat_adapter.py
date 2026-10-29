import httpx
import pytest
from pydantic import SecretStr
from app.core.config import Settings
from app.core.exceptions import BusinessError
from app.services.chat.llm import QwenClient


def settings():
    return Settings(_env_file=None,llm_base_url='https://example.test/v1',llm_api_key=SecretStr('test-only-secret'),llm_model='test-qwen')


def transport(monkeypatch,handler):
    original=httpx.Client
    monkeypatch.setattr('app.services.chat.llm.httpx.Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))


def test_chat_json_contract(monkeypatch):
    import json
    def handler(request):
        assert request.url.path=='/v1/chat/completions'
        body=json.loads(request.content)
        assert body['model']=='test-qwen' and body['response_format']=={'type':'json_object'}
        assert body['messages'][0]['role']=='system'
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"supported":true}'}}]})
    transport(monkeypatch,handler)
    assert QwenClient(settings()).complete_json('system',{'question':'问题'})=={'supported':True}


@pytest.mark.parametrize('payload',[
    {'choices':[{'finish_reason':'length','message':{'content':'{}'}}]},
    {'choices':[{'finish_reason':'stop','message':{'content':'not-json'}}]},
    {'choices':[]},
])
def test_malformed_or_truncated_response_is_controlled(monkeypatch,payload):
    transport(monkeypatch,lambda request:httpx.Response(200,json=payload))
    with pytest.raises(BusinessError) as error: QwenClient(settings()).complete_json('test',{})
    assert error.value.status_code==502


def test_http_errors_never_expose_provider_body(monkeypatch):
    transport(monkeypatch,lambda request:httpx.Response(401,text='test-only-secret'))
    with pytest.raises(BusinessError) as error: QwenClient(settings()).complete_json('test',{})
    assert 'test-only-secret' not in error.value.message and '401' in error.value.message


def test_timeout_and_missing_config(monkeypatch):
    def handler(request): raise httpx.ReadTimeout('test-only-secret',request=request)
    transport(monkeypatch,handler)
    with pytest.raises(BusinessError) as error: QwenClient(settings()).complete_json('test',{})
    assert error.value.status_code==504
    with pytest.raises(BusinessError): QwenClient(Settings(_env_file=None)).ensure_configured()
