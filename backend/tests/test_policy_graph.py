from types import SimpleNamespace
import pytest
from app.agents.orchestrator import run_policy
from app.schemas.chat import PolicyQuestion
from app.schemas.retrieval import SearchHit
from app.core.exceptions import BusinessError


class Model:
    model = 'test-qwen'
    def __init__(self, *responses): self.responses=list(responses); self.calls=[]; self.review_calls=[]; self.review_response=None
    def review_json(self,system,payload):
        self.review_calls.append(payload)
        if isinstance(self.review_response,Exception): raise self.review_response
        if self.review_response is not None:
            import copy
            response=copy.deepcopy(self.review_response)
            for item in response.get('assessments',[]): item.setdefault('addresses_question',True)
            return response
        return {'assessments':[{'paragraph':p['paragraph'],'policy_type':'other','supported':True,'addresses_question':True,'reason':'supported',
            'quotes':[{'source_index':p['sources'][0],'text':next(e['text'] for e in payload['evidence'] if e['index']==p['sources'][0])[:1600]}]} for p in payload['paragraphs']]}
    def ensure_configured(self): pass
    def complete_json(self, system, payload):
        self.calls.append(payload)
        return self.responses.pop(0)


def decision(**updates):
    return dict(supported=True, needs_clarification=False, clarification='', query='杭州市养老补贴申请', **updates)


def hit(index=1):
    return SearchHit(chunk_id=index,doc_id='policy',kb_id='general',doc_name='政策说明',type='TXT',source='本地上传',
        seq=index,start=0,end=12,chars=12,text='杭州市养老补贴向社区申请。',score=2/61,cos=.8,lexical_score=1.2)


def setup_retrieval(monkeypatch, hits):
    from app.agents import orchestrator
    calls=[]
    def retrieve(db, request, embedder, manager, allowed_kb_ids):
        calls.append((request,allowed_kb_ids))
        return SimpleNamespace(hits=hits,log_id='retrieval-1',vector_count=10)
    monkeypatch.setattr(orchestrator.hybrid,'search',retrieve)
    return calls


def run(model, question=None):
    return run_policy(question or PolicyQuestion(question='怎么办理'), None, SimpleNamespace(ensure_configured=lambda:None), None, model, ['policies'])


def test_clarification_skips_retrieval_and_preserves_history(monkeypatch):
    calls=setup_retrieval(monkeypatch,[])
    d=decision();d.update(needs_clarification=True,clarification='请问老人所在的城市是哪里？')
    model=Model(d)
    result=run(model,PolicyQuestion(question='可以申请吗',history=[{'role':'user','content':'我想申请长护险'}]))
    assert result.status=='clarification' and not calls and result.citations==[]
    assert model.calls[0]['history'][0]['content']=='我想申请长护险'
    assert result.steps==['understand','clarify']


def test_no_hits_does_not_generate(monkeypatch):
    calls=setup_retrieval(monkeypatch,[])
    model=Model(decision())
    result=run(model)
    assert result.status=='insufficient' and len(model.calls)==1
    assert calls[0][1]==['policies'] and result.retrieval_log_id=='retrieval-1'


def test_answer_and_sparse_citations_use_actual_source_indices(monkeypatch):
    setup_retrieval(monkeypatch,[hit(1),hit(2)])
    model=Model(decision(),{'sufficient':True,'paragraphs':[{'text':'可以向社区咨询申请。','sources':[2]}]})
    result=run(model)
    assert result.status=='answered' and '【2】' in result.answer
    assert [c.index for c in result.citations]==[2]
    assert result.citations[0].hit.chunk_id==2
    assert result.steps==['understand','retrieve','generate','validate_citations','verify_grounding']
    assert 'evidence' in model.calls[1] and 'history' not in model.calls[1]


@pytest.mark.parametrize('draft',[
    {'sufficient':True,'paragraphs':[{'text':'无依据结论','sources':[99]}]},
    {'sufficient':True,'paragraphs':[{'text':'无引用','sources':[]}]},
    {'sufficient':True,'paragraphs':[{'text':'伪造【1】','sources':[1]}]},
    {'sufficient':False,'paragraphs':[]},
    {'sufficient':True,'paragraphs':[{'text':'坏类型','sources':[True]}]},
])
def test_invalid_or_insufficient_draft_fails_closed(monkeypatch,draft):
    setup_retrieval(monkeypatch,[hit()])
    result=run(Model(decision(),draft,draft))
    assert result.status=='insufficient' and result.citations==[] and '无依据结论' not in result.answer


def test_context_is_bounded_and_matches_citation(monkeypatch):
    source=hit().model_copy(update={'text':'政'*8000,'chars':8000,'end':8000})
    setup_retrieval(monkeypatch,[source])
    model=Model(decision(),{'sufficient':True,'paragraphs':[{'text':'政策说明','sources':[1]}]})
    result=run(model)
    assert len(model.calls[1]['evidence'][0]['text'])==4000
    assert result.citations[0].hit.text==model.calls[1]['evidence'][0]['text']
    assert result.citations[0].hit.end==4000


def test_invalid_understanding_returns_controlled_error():
    with pytest.raises(BusinessError) as error: run(Model({'query':'test'}, {'query':'test'}))
    assert error.value.status_code==502


@pytest.mark.parametrize('d',[
    {'supported':True,'needs_clarification':True,'clarification':'请问所在城市？','query':None},
    {'supported':True,'needs_clarification':True,'clarification':'请问所在城市？'},
    {'supported':False,'needs_clarification':False,'clarification':None,'query':None},
])
def test_nonretrieval_branch_does_not_require_query(monkeypatch,d):
    calls=setup_retrieval(monkeypatch,[])
    result=run(Model(d))
    assert result.status=='clarification' and calls==[]


def test_null_unused_clarification_is_valid(monkeypatch):
    setup_retrieval(monkeypatch,[])
    result=run(Model({'supported':True,'needs_clarification':False,'clarification':None,'query':'养老政策'}))
    assert result.status=='insufficient'


def test_bad_schema_gets_one_bounded_repair_attempt(monkeypatch):
    setup_retrieval(monkeypatch,[])
    model=Model({'supported':'true','needs_clarification':False,'query':'养老政策'},decision())
    result=run(model)
    assert result.status=='insufficient' and len(model.calls)==2
    assert 'format_retry' in model.calls[1]
    assert 'supported' in str(model.calls[1]['format_retry']['issues'])


def test_retrieval_still_requires_nonblank_query(monkeypatch):
    calls=setup_retrieval(monkeypatch,[])
    bad={'supported':True,'needs_clarification':False,'query':None}
    with pytest.raises(BusinessError): run(Model(bad,bad))
    assert calls==[]


def test_clarification_still_requires_question(monkeypatch):
    calls=setup_retrieval(monkeypatch,[])
    bad={'supported':True,'needs_clarification':True,'clarification':None}
    with pytest.raises(BusinessError): run(Model(bad,bad))
    assert calls==[]


def test_general_elderly_activities_question_explains_boundary(monkeypatch):
    calls=setup_retrieval(monkeypatch,[])
    model=Model({'supported':False,'needs_clarification':False,'query':None,'clarification':None})
    result=run(model,PolicyQuestion(question='养老活动有哪些'))
    assert result.status=='clarification' and '政策顾问' in result.answer
    assert '养老政策' in result.answer and not calls
    assert model.calls[0]['question']=='养老活动有哪些'


def test_retrieved_evidence_is_preserved_when_model_declines(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    result=run(Model(decision(),{'sufficient':False,'paragraphs':[]}))
    assert result.reason=='model_insufficient' and len(result.retrieved_hits)==1
    assert not result.citations and result.vector_count==10


def test_format_failure_is_not_reported_as_empty_retrieval(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    result=run(Model(decision(),{'unexpected':'data'},{'unexpected':'data'}))
    assert result.reason=='invalid_output' and result.retrieved_hits
    assert '格式' in result.answer


def test_hangzhou_overview_retrieves_and_answers_supported_subset(monkeypatch):
    calls=setup_retrieval(monkeypatch,[hit()])
    d=decision();d['query']='杭州市 高龄及困难老年人补贴 制度'
    result=run(Model(d,{'sufficient':True,'paragraphs':[{'text':'这份资料覆盖高龄及困难老年人补贴，不代表全部养老补贴。','sources':[1]}]}),PolicyQuestion(question='杭州市的养老补贴是怎么样的'))
    assert result.status=='answered' and calls[0][0].query=='杭州市的养老补贴是怎么样的'
    assert result.retrieved_hits and result.reason=='grounded_answer'


def test_generation_repairs_format_without_losing_evidence(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    model=Model(decision(),{'sufficient':True,'paragraphs':[{'text':'政策说明【1】','sources':[1]}]},
        {'sufficient':True,'paragraphs':[{'text':'政策说明','sources':[1]}]})
    result=run(model)
    assert result.status=='answered' and len(model.calls)==3
    assert model.calls[1]['evidence']==model.calls[2]['evidence']
    assert 'format_retry' in model.calls[2]
