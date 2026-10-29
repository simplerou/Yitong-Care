import json
import httpx
import pytest
from pydantic import SecretStr
from app.core.config import Settings
from app.services.web.tavily import TavilySearch, WebSearchError


def service(**updates):
    return TavilySearch(Settings(_env_file=None,tavily_api_key=SecretStr('test-only-secret'),**updates))


def mock_http(monkeypatch, handler):
    original=httpx.Client
    monkeypatch.setattr('app.services.web.tavily.httpx.Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))


def test_search_extracts_only_allowlisted_body_not_snippets(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request.url.path)
        body=json.loads(request.content)
        assert request.headers['Authorization']=='Bearer test-only-secret'
        if request.url.path=='/search':
            assert body['include_domains']==['gov.cn'] and not body['include_answer']
            return httpx.Response(200,json={'results':[
                {'title':'官方补贴通知','url':'https://mz.hangzhou.gov.cn/policy#top','content':'不可用搜索摘要作答'},
                {'title':'伪站点','url':'https://gov.cn.evil.test/policy'},
                {'title':'不可信','url':'javascript:alert(1)'}]})
        assert body['urls']==['https://mz.hangzhou.gov.cn/policy']
        return httpx.Response(200,json={'results':[
            {'url':'https://mz.hangzhou.gov.cn/policy','raw_content':'杭州市养老补贴原文'*1000},
            {'url':'https://elsewhere.gov.cn/other','raw_content':'非请求页面'},
            {'url':'https://mz.hangzhou.gov.cn/policy','raw_content':'重复'}]})
    mock_http(monkeypatch,handler)
    result=service().search('杭州市养老补贴')
    assert calls==['/search','/extract'] and len(result)==1
    assert result[0].content==('杭州市养老补贴原文'*1000)[:4000] and result[0].published_date is None
    assert result[0].retrieved_at and result[0].title=='官方补贴通知'


@pytest.mark.parametrize('url',['https://gov.cn.evil.test/x','https://evilgov.cn','file:///tmp/x','http://localhost/x','https://user:secret@x.gov.cn/x','https://x.gov.cn:9000/x'])
def test_reject_unsafe_or_outside_domain(url):
    assert service().allowed_url(url) is None


def test_disabled_never_requests_network(monkeypatch):
    monkeypatch.setattr(httpx,'Client',lambda **kw:pytest.fail('must not call'))
    assert TavilySearch(Settings(_env_file=None)).search('test')==[]


def test_search_snippets_without_extracted_body_are_not_evidence(monkeypatch):
    def handler(request):
        return httpx.Response(200,json={'results':[{'url':'https://hangzhou.gov.cn/x','content':'snippet','raw_content':None}]})
    mock_http(monkeypatch,handler)
    assert service().search('test')==[]


def test_http_failure_is_safe(monkeypatch):
    mock_http(monkeypatch,lambda r:httpx.Response(401,text='test-only-secret'))
    with pytest.raises(WebSearchError) as error: service().search('test')
    assert '401' in str(error.value) and 'test-only-secret' not in str(error.value)


def test_extract_failure_and_timeout(monkeypatch):
    def handler(request):
        if request.url.path=='/search': return httpx.Response(200,json={'results':[{'url':'https://hangzhou.gov.cn/x'}]})
        raise httpx.ReadTimeout('secret',request=request)
    mock_http(monkeypatch,handler)
    with pytest.raises(WebSearchError,match='超时'): service().search('test')


def test_diagnostics_distinguish_filter_rejection_and_extraction_failure(monkeypatch):
    def handler(request):
        if request.url.path=='/search':
            return httpx.Response(200,json={'results':[
                {'title':'经济发展','url':'https://hangzhou.gov.cn/economy'},
                {'title':'高龄补贴通知','url':'https://hangzhou.gov.cn/policy'},
                {'title':'高龄补贴附件','url':'https://hangzhou.gov.cn/missing'},
                {'title':'其他','url':'https://outside.test'}]})
        return httpx.Response(200,json={'results':[
            {'url':'https://hangzhou.gov.cn/economy','raw_content':'支持企业上市和工业项目投资。'},
            {'url':'https://hangzhou.gov.cn/policy','raw_content':'本市高龄老年人补贴按年龄发放。'}],
            'failed_results':[{'url':'https://hangzhou.gov.cn/missing','error':'blocked'}]})
    mock_http(monkeypatch,handler)
    report=service().search_with_diagnostics('杭州市最新高龄津贴政策')
    d=report.diagnostics
    assert len(report.sources)==1 and d.stage=='complete'
    assert (d.search_count,d.official_count,d.extraction_requested,d.extraction_returned,d.body_count,d.accepted_count)==(4,3,3,2,2,1)
    assert d.rejected_counts['url_not_allowed']==1
    assert d.rejected_counts['extraction_failed']==1
    assert d.rejected_counts['benefit_missing']==1
    assert {page.reason for page in d.pages}=={'benefit_missing','relevant','extraction_failed'}


def test_empty_search_is_different_from_empty_extraction(monkeypatch):
    mock_http(monkeypatch,lambda r:httpx.Response(200,json={'results':[]}))
    d=service().search_with_diagnostics('杭州市高龄津贴').diagnostics
    assert d.stage=='complete' and d.search_count==0 and d.extraction_requested==0


def test_network_failure_keeps_stage_diagnostics(monkeypatch):
    def handler(request): raise httpx.ConnectError('do not expose secret',request=request)
    mock_http(monkeypatch,handler)
    with pytest.raises(WebSearchError) as error: service().search_with_diagnostics('test')
    assert error.value.diagnostics.stage=='search'
    assert 'secret' not in str(error.value)


def test_more_candidates_are_screened_before_final_result_limit(monkeypatch):
    def handler(request):
        if request.url.path=='/search':
            import json
            assert json.loads(request.content)['max_results']==3
            return httpx.Response(200,json={'results':[{'url':f'https://hangzhou.gov.cn/{i}'} for i in range(3)]})
        return httpx.Response(200,json={'results':[
            {'url':'https://hangzhou.gov.cn/0','raw_content':'无关经济政策'},
            {'url':'https://hangzhou.gov.cn/1','raw_content':'本市高龄老年人补贴。'},
            {'url':'https://hangzhou.gov.cn/2','raw_content':'本市高龄老年人津贴。'}]})
    mock_http(monkeypatch,handler)
    report=service(tavily_max_results=1).search_with_diagnostics('杭州市高龄津贴')
    assert len(report.sources)==1 and report.sources[0].url.endswith('/1')
    assert report.diagnostics.rejected_counts['output_limit']==1


def test_extract_metadata_never_certifies_complete_policy(monkeypatch):
    body='杭州市高龄老年人补贴通知。'*500
    def handler(request):
        if request.url.path=='/search': return httpx.Response(200,json={'results':[{'url':'https://hangzhou.gov.cn/policy'}]})
        return httpx.Response(200,json={'results':[{'url':'https://hangzhou.gov.cn/policy','raw_content':body}]})
    mock_http(monkeypatch,handler)
    source=service().search('杭州市高龄补贴')[0]
    assert source.is_truncated and source.coverage=='excerpt'
    assert source.original_content_chars==len(body) and source.excerpt_start>=0
    assert source.completeness_verified is False
