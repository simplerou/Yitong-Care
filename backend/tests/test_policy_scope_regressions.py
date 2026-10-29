import json
from pathlib import Path
import pytest
from app.schemas.chat import PolicyQuestion
from app.services.chat.citation import Draft
from app.services.chat.grounding import numeric_support_issues
from test_policy_graph import Model, decision, hit, setup_retrieval, run

FIXTURES=json.loads((Path(__file__).parent/'fixtures/policy_scope_regressions.json').read_text())


@pytest.mark.parametrize('fixture',FIXTURES,ids=lambda f:f['case'])
def test_actual_failed_drafts_are_caught_before_review(fixture):
    parsed=Draft.model_validate(fixture['draft'])
    issues=numeric_support_issues(parsed.paragraphs,fixture['evidence'])
    expected='age_not_in_evidence' if fixture['case']=='P03' else 'amount_not_in_evidence'
    assert expected in {issue['type'] for issue in issues}


@pytest.mark.parametrize('fixture',FIXTURES,ids=lambda f:f['case'])
def test_original_question_is_not_expanded_and_draft_can_be_corrected(monkeypatch,fixture):
    sources=[hit(i).model_copy(update={'text':item['text']}) for i,item in enumerate(fixture['evidence'],1)]
    setup_retrieval(monkeypatch,sources)
    d=decision();d['query']=fixture['rewritten_query']
    text='根据该文件，西湖区户籍90周岁及以上老年人的养老服务补贴为每人每月100元。' if fixture['case']=='P03' else '低边家庭轻度失能老年人补贴标准按不低于低保家庭轻度失能老年人补贴标准的50%执行；低保家庭轻度失能老年人的标准为每人每月125元。'
    good={'sufficient':True,'paragraphs':[{'text':text,'sources':[1]}]}
    model=Model(d,fixture['draft'],good)
    result=run(model,PolicyQuestion(question=fixture['question']))
    assert result.status=='answered',result.answer
    assert model.calls[1]['question']==fixture['question']
    if len(model.calls)>2:
        assert 'format_retry' in model.calls[2]
        assert text in result.answer
    else:
        assert fixture['case']=='P06' and '不低于' in result.answer and '50%' in result.answer
    assert '62.5元' not in result.answer and '90-99' not in result.answer


def test_repeat_numeric_hallucination_never_reaches_semantic_reviewer(monkeypatch):
    setup_retrieval(monkeypatch,[hit().model_copy(update={'text':'80周岁每月40元。'})])
    bad={'sufficient':True,'paragraphs':[{'text':'70周岁每月400元。','sources':[1]}]}
    model=Model(decision(),bad,bad)
    result=run(model,PolicyQuestion(question='高龄补贴标准是多少？'))
    assert result.reason=='unsupported_numeric_expansion' and not model.review_calls


def test_actual_p06_calculation_drafts_keep_the_original_rule(monkeypatch):
    fixture=json.loads((Path(__file__).parent/'fixtures/policy_calculation_regression.json').read_text())
    for output in fixture['drafts']:
        sources=[hit(i).model_copy(update={'text':e['text']}) for i,e in enumerate(fixture['evidence'],1)]
        setup_retrieval(monkeypatch,sources)
        d=decision();d['needs_freshness']=True
        model=Model(d,output)
        result=run(model,PolicyQuestion(question=fixture['question']))
        assert result.status=='answered',result.answer
        assert '不低于' in result.answer and '50%' in result.answer and '62.5元' not in result.answer
        assert 'web_search' not in result.steps
        assert len(model.calls)==2
