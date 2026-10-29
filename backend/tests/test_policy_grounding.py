from app.core.exceptions import BusinessError
from test_policy_graph import Model, decision, hit, setup_retrieval, run


def draft():
    return {'sufficient':True,'paragraphs':[{'text':'高龄老人可咨询社区申请补贴。','sources':[1]}]}


def review(reason='supported',supported=True,policy_type='high_age',quote='杭州市养老补贴向社区申请。'):
    return {'assessments':[{'paragraph':1,'policy_type':policy_type,'supported':supported,'reason':reason,
        'quotes':[{'source_index':1,'text':quote}] if supported else []}]}


def test_category_confusion_is_blocked(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    model=Model(decision(),draft());model.review_response=review('category_mismatch',False)
    result=run(model)
    assert result.reason=='unsupported_policy_claim' and not result.citations
    assert result.answer_checks.status=='blocked' and result.retrieved_hits


def test_review_adds_policy_type_and_only_uses_cited_evidence(monkeypatch):
    setup_retrieval(monkeypatch,[hit(),hit(2)])
    model=Model(decision(),draft());model.review_response=review()
    result=run(model)
    assert result.answer_checks.status=='passed' and '高龄补贴／津贴' in result.policy_categories
    assert [e['index'] for e in model.review_calls[0]['evidence']]==[1]
    assert result.steps[-1]=='verify_grounding'


def test_reviewer_failure_never_releases_unchecked_draft(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    model=Model(decision(),draft());model.review_response=BusinessError('timeout',504)
    result=run(model)
    assert result.answer_checks.status=='error' and result.reason=='grounding_review_failed'
    assert not result.citations and result.status=='insufficient'


def test_partial_review_keeps_only_supported_paragraphs_and_citations(monkeypatch):
    setup_retrieval(monkeypatch,[hit(),hit(2)])
    d=draft();d['paragraphs'].append({'text':'未经支持的失能护理待遇。','sources':[2]})
    model=Model(decision(),d)
    output=review();output['assessments'].append({'paragraph':2,'policy_type':'disability_care','supported':False,'reason':'missing_conditions','quotes':[]})
    model.review_response=output
    result=run(model)
    assert result.answer_checks.status=='partial' and result.answer_checks.accepted_paragraphs==1
    assert [c.index for c in result.citations]==[1]
    assert '未经支持' not in result.answer and '已省略' in result.answer


def test_date_only_survivor_does_not_count_as_amount_answer(monkeypatch):
    from app.schemas.chat import PolicyQuestion
    setup_retrieval(monkeypatch,[hit().model_copy(update={'text':'90周岁每月100元。文件有公布日期。'})])
    d=decision();d['query']='90周岁高龄补贴标准是多少'
    output={'sufficient':True,'paragraphs':[{'text':'90周岁每月100元。','sources':[1]},{'text':'文件有公布日期。','sources':[1]}]}
    model=Model(d,output)
    model.review_response={'assessments':[
        {'paragraph':1,'policy_type':'high_age','supported':False,'reason':'missing_conditions','quotes':[]},
        {'paragraph':2,'policy_type':'other','supported':True,'reason':'supported','quotes':[{'source_index':1,'text':'文件有公布日期。'}]}]}
    result=run(model,PolicyQuestion(question='90周岁高龄补贴标准是多少'))
    assert result.reason=='answer_incomplete' and not result.citations
    assert result.answer_checks.status=='blocked' and 'core_answer_removed' in result.answer_checks.issues


def test_supported_but_irrelevant_paragraph_does_not_count_as_answer(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    model=Model(decision(),draft())
    output=review();output['assessments'][0]['addresses_question']=False
    model.review_response=output
    result=run(model)
    assert result.status=='insufficient' and not result.citations
    assert 'answer_off_topic' in result.answer_checks.issues


def test_reviewer_receives_real_evidence_spans_and_original_question(monkeypatch):
    from app.schemas.chat import PolicyQuestion
    setup_retrieval(monkeypatch,[hit()])
    model=Model(decision(),draft());model.review_response=review()
    result=run(model,PolicyQuestion(question='90岁的呢？'))
    payload=model.review_calls[0]
    assert payload['user_question']=='90岁的呢？'
    assert payload['evidence'][0]['spans'][0]['text']==hit().text


def test_scope_rejected_paragraph_never_reappears_in_final_review(monkeypatch):
    setup_retrieval(monkeypatch,[hit()])
    raw={'sufficient':True,'paragraphs':[{'text':'补贴面向全体户籍高龄老人。','sources':[1]},{'text':'可向社区咨询政策。','sources':[1]}]}
    model=Model(decision(),raw,raw)
    result=run(model)
    assert result.status=='answered' and '全体户籍高龄老人' not in result.answer
    assert len(model.review_calls[0]['paragraphs'])==1
