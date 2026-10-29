from app.agents.orchestrator import run_policy
from app.schemas.chat import PolicyQuestion, WebSource
from app.services.web.tavily import WebSearchError
from types import SimpleNamespace
from test_policy_graph import Model, decision, hit, setup_retrieval


class Web:
    configured=True
    def __init__(self, sources=None, error=None): self.sources=sources or []; self.error=error; self.calls=[]
    def search(self, query):
        self.calls.append(query)
        if self.error: raise WebSearchError(self.error)
        return self.sources


def source():
    return WebSource(title='杭州市官方补贴通知',url='https://mz.hangzhou.gov.cn/policy',content='高龄老年人补贴原文',retrieved_at='2026-10-29T00:00:00Z')


def draft(indices=[1]):
    return {'sufficient':True,'paragraphs':[{'text':'根据所检索的通知解释补贴条件。','sources':indices}]}


def run(model, web, question='杭州市养老补贴怎么样'):
    return run_policy(PolicyQuestion(question=question),None,SimpleNamespace(ensure_configured=lambda:None),None,model,['general'],web=web)


def test_no_local_hits_falls_back_to_web_and_cites_actual_url(monkeypatch):
    setup_retrieval(monkeypatch,[])
    web=Web([source()]);model=Model(decision(),draft())
    result=run(model,web)
    assert result.status=='answered' and result.web_status=='success' and len(web.calls)==1
    assert result.citations[0].source_type=='web' and result.citations[0].hit is None
    assert result.citations[0].web.url==source().url
    assert model.calls[1]['evidence'][0]['text']==source().content


def test_latest_policy_searches_even_with_local_hits(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    web=Web([source()]);model=Model(decision(),draft([1,2]))
    result=run(model,web,'杭州最新养老补贴政策')
    assert result.status=='answered' and result.steps.index('web_search') < result.steps.index('generate')
    assert [c.source_type for c in result.citations]==['local','web']
    assert [c.index for c in result.citations]==[1,2]


def test_standalone_spurious_freshness_flag_does_not_trigger_search(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    d=decision();d['needs_freshness']=True
    result=run(Model(d,draft([1])),Web([source()]))
    assert result.web_status=='not_used' and result.citations[0].index==1


def test_model_insufficient_triggers_exactly_one_web_fallback(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    web=Web([source()])
    result=run(Model(decision(),{'sufficient':False,'paragraphs':[]},draft([2])),web)
    assert result.status=='answered' and len(web.calls)==1


def test_both_sources_insufficient_does_not_loop(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    web=Web([source()]);no={'sufficient':False,'paragraphs':[]}
    result=run(Model(decision(),no,no),web)
    assert result.status=='insufficient' and len(web.calls)==1 and result.web_sources


def test_normal_supported_local_answer_skips_web(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    web=Web([source()])
    result=run(Model(decision(),draft()),web)
    assert result.status=='answered' and not web.calls and result.web_status=='not_used'


def test_missing_key_retains_local_answer_and_warns(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    web=Web();web.configured=False
    result=run(Model(decision(),draft()),web,'杭州最新养老补贴政策')
    assert result.status=='answered' and result.web_status=='not_configured' and not web.calls
    assert '未完成网络核验' in result.answer


def test_failed_network_does_not_erase_local_evidence(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    result=run(Model(decision(),draft()),Web(error='服务超时，未完成网络核验。'),'杭州最新养老补贴政策')
    assert result.web_status=='error' and result.retrieved_hits and result.status=='answered'
    assert '未完成网络核验' in result.answer


def test_empty_web_body_does_not_generate_ungrounded_answer(monkeypatch):
    setup_retrieval(monkeypatch,[])
    model=Model(decision());result=run(model,Web())
    assert result.status=='insufficient' and result.web_status=='no_results' and len(model.calls)==1


def test_unsupported_validity_claim_is_repaired(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    bad={'sufficient':True,'paragraphs':[{'text':'该文件现行有效。','sources':[1]}]}
    model=Model(decision(),bad,draft())
    result=run(model,Web())
    assert result.status=='answered' and '现行有效' not in result.answer
    assert 'format_retry' in model.calls[2]


def test_persistent_validity_hallucination_is_withheld(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    bad={'sufficient':True,'paragraphs':[{'text':'未搜到废止文件，所以仍然有效。','sources':[1]}]}
    result=run(Model(decision(),bad,bad),Web())
    assert result.status=='insufficient' and result.reason=='unsupported_validity_claim'
    assert not result.citations and result.retrieved_hits


def test_safe_policy_paragraph_survives_unsafe_validity_paragraph(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    bad={'sufficient':True,'paragraphs':[{'text':'现行有效的政策如下。','sources':[1]}, {'text':'根据原文件，可向社区咨询补贴。','sources':[1]}]}
    result=run(Model(decision(),bad,bad),Web())
    assert result.status=='answered' and '现行有效的政策如下' not in result.answer
    assert '根据原文件' in result.answer and '尚不能确认' in result.answer


def test_search_report_diagnostics_are_returned_to_chat(monkeypatch):
    from app.services.web.tavily import SearchReport
    from app.schemas.chat import WebDiagnostics
    setup_retrieval(monkeypatch,[])
    class ReportingWeb:
        configured=True
        def search_with_diagnostics(self,query):
            return SearchReport([source()],WebDiagnostics(stage='complete',search_count=3,body_count=2,accepted_count=1))
    result=run(Model(decision(),draft()),ReportingWeb())
    assert result.web_diagnostics.search_count==3 and result.web_diagnostics.accepted_count==1
