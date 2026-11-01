from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4
import pytest
from pydantic import ValidationError, SecretStr
from app.schemas.policy import PolicyMetadata
from app.services.retrieval.context import expand_hit
from app.services.web.cache import SearchCache
from app.services.web.tavily import TavilySearch, SearchReport, WebSearchError
from app.schemas.chat import WebSource, WebDiagnostics
from app.core.config import Settings
from test_policy_graph import hit, Model, decision, setup_retrieval, run


def test_metadata_requires_dated_verification_and_consistent_dates():
    assert PolicyMetadata().validity == 'unknown'
    for fields in [dict(validity='effective'),dict(effective_on='2026-02-02',expires_on='2026-01-01'),
                   dict(verified_on=date.today()+timedelta(days=1)),dict(regions=[''])]:
        with pytest.raises(ValidationError): PolicyMetadata(**fields)
    assert PolicyMetadata(validity='repealed',verified_on=date.today(),verification_source='主管部门废止公告').validity=='repealed'


def test_context_expansion_retains_exact_source_offsets_and_table_header():
    text='一、补贴标准\n适用对象：80周岁以上本市户籍。\n年龄\t每月金额\n90周岁\t100元\n以上限所列地区为准。'
    start=text.index('90周岁')
    source=hit().model_copy(update=dict(text='90周岁\t100元',start=start,end=start+len('90周岁\t100元')))
    expanded=expand_hit(source,SimpleNamespace(content=text))
    assert expanded.text == text[expanded.start:expanded.end]
    assert '适用对象' in expanded.text and '每月金额' in expanded.text
    assert expanded.matched_start==start and expanded.context_expanded
    assert expanded.heading=='一、补贴标准'
    assert expand_hit(source,SimpleNamespace(content='changed')) == source


def test_context_expansion_never_exceeds_budget_or_drops_match():
    body='甲'*5000+'原始命中'+'乙'*5000
    source=hit().model_copy(update=dict(text='原始命中',start=5000,end=5004))
    result=expand_hit(source,SimpleNamespace(content=body),budget=1000,margin=600)
    assert len(result.text)<=1000 and '原始命中' in result.text
    assert result.text==body[result.start:result.end]


def test_cache_ttl_eviction_and_copy_isolation():
    now=[0]
    cache=SearchCache(capacity=2,clock=lambda:now[0])
    cache.put('a',{'items':[1]},10)
    copy=cache.get('a');copy['items'].append(2)
    assert cache.get('a')=={'items':[1]}
    cache.put('b',2,10);cache.put('c',3,10)
    assert cache.get('a') is None
    now[0]=10
    assert cache.get('c') is None and not cache.items
    cache.put('d',4,0);assert cache.get('d') is None


def report():
    return SearchReport([WebSource(title='官方养老服务',url='https://hangzhou.gov.cn/x',content='养老服务条款',retrieved_at='2026-10-01T00:00:00Z')],WebDiagnostics(stage='complete'))


def test_search_cache_freshness_settings_and_failures(monkeypatch):
    import app.services.web.cache as module
    monkeypatch.setattr(module,'search_cache',SearchCache())
    service=TavilySearch(Settings(_env_file=None,tavily_api_key=SecretStr('test')))
    calls=[]
    def fetch(query): calls.append(query);return report()
    monkeypatch.setattr(service,'_search_with_diagnostics',fetch)
    original=service.search_with_diagnostics('养老服务办理')
    cached=service.search_with_diagnostics('养老服务办理')
    assert len(calls)==1 and cached.diagnostics.cache_hit and not original.diagnostics.cache_hit
    assert cached.sources[0].retrieved_at==original.sources[0].retrieved_at
    for question in ['最新养老政策','养老政策还有效吗','2026年养老标准']:
        service.search_with_diagnostics(question);service.search_with_diagnostics(question)
    assert len(calls)==7
    service.search_with_diagnostics('养老服务办理',bypass_cache=True)
    assert len(calls)==8
    service.settings.tavily_include_domains=['example.gov.cn']
    service.search_with_diagnostics('养老服务办理');assert len(calls)==9
    def fail(query): calls.append(query);raise WebSearchError('网络异常')
    monkeypatch.setattr(service,'_search_with_diagnostics',fail)
    for _ in range(2):
        with pytest.raises(WebSearchError): service.search_with_diagnostics('失败场景')
    assert calls[-2:]==['失败场景','失败场景']


def test_workflow_uses_explicit_context_and_emits_stages(monkeypatch):
    from app.agents.orchestrator import run_policy
    from app.schemas.chat import PolicyQuestion
    retrieval=setup_retrieval(monkeypatch,[])
    stages=[]
    model=Model(decision())
    answer=run_policy(PolicyQuestion(question='这种补贴怎么办理',context={'region':'杭州市','age':90,'benefit':'养老服务补贴'}),None,SimpleNamespace(ensure_configured=lambda:None),None,model,['general'],progress=stages.append)
    assert model.calls[0]['confirmed_context']['age']==90
    assert answer.consultation_context.region=='杭州市'
    assert stages==['understand','retrieve','web_search','insufficient']
    assert '杭州市' in retrieval[0][0].query
    long_question='养老政策咨询'*166+'养老咨询'
    run_policy(PolicyQuestion(question=long_question,context={'region':'杭州市'}),None,SimpleNamespace(ensure_configured=lambda:None),None,Model(decision()),['general'])
    assert retrieval[-1][0].query == long_question


def test_token_usage_is_request_scoped_and_missing_is_unknown():
    from app.services.chat.metrics import MeasuredLLM, PolicyMetrics, record_usage
    class Client:
        def complete_json(self): record_usage({'prompt_tokens':10,'completion_tokens':4});return {}
    metrics=PolicyMetrics();MeasuredLLM(Client(),metrics).complete_json()
    record_usage({'prompt_tokens':999,'completion_tokens':999})
    assert metrics.snapshot()['prompt_tokens']==10 and metrics.usage_calls==1
    assert PolicyMetrics().snapshot()['prompt_tokens'] is None
