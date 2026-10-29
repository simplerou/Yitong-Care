import pytest
from app.services.chat.grounding import Review, evaluate_review
from app.services.chat.citation import Paragraph


def check(answer,quote,body=None,source=1,policy_type='high_age'):
    paragraphs=[Paragraph(text=answer,sources=[1])]
    review=Review.model_validate({'assessments':[{'paragraph':1,'policy_type':policy_type,'supported':True,'reason':'supported',
        'quotes':[{'source_index':source,'text':quote}]}]})
    return evaluate_review(review,paragraphs,[{'index':1,'text':body or quote}])


def test_numeric_age_and_cycle_anchors_match():
    body='本市户籍80至89周岁老年人，每人每月40元。'
    accepted,issues=check('本市户籍80—89周岁老人每月40元。',body)
    assert accepted and not issues


@pytest.mark.parametrize('answer,quote,reason',[
 ('80至89周岁每月400元。','80至89周岁每月40元。','amount_not_in_quote'),
 ('70周岁每月40元。','80周岁每月40元。','age_not_in_quote'),
 ('80周岁每年40元。','80周岁每月40元。','payment_cycle_mismatch'),
])
def test_numbers_cannot_be_hallucinated_even_if_reviewer_approves(answer,quote,reason):
    accepted,issues=check(answer,quote)
    assert not accepted and issues==[reason]


def test_fabricated_quote_and_uncited_source_are_rejected():
    assert check('补贴40元','补贴40元','原文没有该金额')[1]==['quote_not_found']
    assert check('政策说明','政策说明',source=2)[1]==['quote_source_mismatch']


def test_review_requires_every_paragraph_once():
    duplicate=Review.model_validate({'assessments':[{'paragraph':1,'policy_type':'other','supported':False,'reason':'unsupported_claim','quotes':[]}]*2})
    with pytest.raises(ValueError): evaluate_review(duplicate,[Paragraph(text='说明',sources=[1])],[])


def test_whitespace_and_fullwidth_amounts_normalize():
    accepted,issues=check('每月４０元。','每月 40 元。','每月\n40 元。')
    assert accepted and not issues


def test_missing_numeric_quote_can_be_repaired_from_actual_evidence():
    from app.services.chat.grounding import review_with_repair
    from types import SimpleNamespace
    paragraphs=[Paragraph(text='90周岁每月100元。',sources=[1])]
    evidence=[{'index':1,'text':'80至89周岁每月40元；90周岁及以上每人每月100元。'}]
    def assessment(quote):
        return {'assessments':[{'paragraph':1,'policy_type':'high_age','supported':True,'reason':'supported','quotes':[{'source_index':1,'text':quote}]}]}
    responses=[assessment('80至89周岁每月40元'),assessment('90周岁及以上每人每月100元')]
    payloads=[]
    def review(system,payload): payloads.append(payload);return responses.pop(0)
    accepted,issues,attempts=review_with_repair(SimpleNamespace(review_json=review),{'question':'90岁多少钱'},paragraphs,evidence)
    assert accepted and not issues and attempts==2
    assert 'review_retry' in payloads[1]


def test_review_schema_gets_one_retry_then_reports_specific_error():
    from app.services.chat.grounding import review_with_repair, GroundingReviewError
    from types import SimpleNamespace
    with pytest.raises(GroundingReviewError) as error:
        review_with_repair(SimpleNamespace(review_json=lambda *args:{}),{},[Paragraph(text='说明',sources=[1])],[])
    assert error.value.code=='review_schema_invalid' and error.value.attempts==2


def test_retry_does_not_allow_fabricated_support():
    from app.services.chat.grounding import review_with_repair
    from types import SimpleNamespace
    raw={'assessments':[{'paragraph':1,'policy_type':'high_age','supported':True,'reason':'supported','quotes':[{'source_index':1,'text':'补贴400元'}]}]}
    accepted,issues,attempts=review_with_repair(SimpleNamespace(review_json=lambda *args:raw),{},[Paragraph(text='补贴400元',sources=[1])],[{'index':1,'text':'补贴40元'}])
    assert not accepted and issues==['quote_not_found'] and attempts==2


def test_span_based_quotes_select_original_without_copying_numbers():
    text='本市户籍80至89周岁每月40元；90周岁及以上每人每月100元。'
    raw={'assessments':[{'paragraph':1,'policy_type':'high_age','supported':True,'addresses_question':True,'reason':'supported','quotes':[{'source_index':1,'span_ids':[1]}]}]}
    accepted,issues=evaluate_review(Review.model_validate(raw),[Paragraph(text='90周岁及以上每月100元。',sources=[1])],[{'index':1,'text':text}])
    assert accepted and not issues
    raw['assessments'][0]['quotes'][0]['span_ids']=[999]
    accepted,issues=evaluate_review(Review.model_validate(raw),[Paragraph(text='90周岁每月100元',sources=[1])],[{'index':1,'text':text}])
    assert not accepted and issues==['span_not_found']


def test_only_trailing_unquoted_calculation_is_removed():
    from app.services.chat.grounding import remove_extra_calculation
    evidence=[{'index':1,'text':'低保家庭轻度失能老年人每人每月125元。低边家庭轻度失能补贴不低于低保家庭轻度标准的50%。'}]
    p=Paragraph(text='低边家庭轻度失能补贴不低于低保家庭轻度标准的50%；低保家庭轻度标准为每人每月125元。因此下限为62.5元/月。',sources=[1])
    result=remove_extra_calculation(p,evidence)
    assert '50%' in result.text and '125元' in result.text and '62.5' not in result.text
    assert result.sources==[1]


def test_without_supported_percentage_rule_no_sentence_is_silently_deleted():
    from app.services.chat.grounding import remove_extra_calculation
    p=Paragraph(text='补贴适用于老年人。因此每月400元。',sources=[1])
    assert remove_extra_calculation(p,[{'index':1,'text':'补贴每月40元。'}])==p
    p=Paragraph(text='原文补贴为125元。因此不低于50%。',sources=[1])
    assert remove_extra_calculation(p,[{'index':1,'text':'原文补贴为125元。'}])==p


def test_real_p04_review_can_complete_age_from_another_already_cited_source():
    import json
    from pathlib import Path
    from app.services.chat.citation import Draft
    data=json.loads((Path(__file__).parents[1]/'fixtures/policy_multi_source_quote.json').read_text())
    paragraphs=Draft.model_validate(data['draft']).paragraphs
    accepted,issues=evaluate_review(Review.model_validate(data['review']),paragraphs,data['evidence'])
    assert not issues and accepted
    assert {q.source_index for q in accepted[1].quotes}=={2,5}


def test_anchor_completion_does_not_borrow_uncited_age():
    raw={'assessments':[{'paragraph':1,'policy_type':'elderly_service','supported':True,'addresses_question':True,'reason':'supported','quotes':[{'source_index':1,'span_ids':[1]}]}]}
    paragraph=Paragraph(text='60周岁及以上每月125元。',sources=[1])
    accepted,issues=evaluate_review(Review.model_validate(raw),[paragraph],[{'index':1,'text':'每月125元。'},{'index':2,'text':'对象为60周岁及以上。'}])
    assert not accepted and issues==['age_not_in_quote']


def test_living_allowance_is_separate_from_elderly_service_subsidy():
    from app.services.chat.grounding import Assessment, LABELS
    item=Assessment(paragraph=1,policy_type='living_allowance',supported=True,addresses_question=True,reason='supported',quotes=[])
    assert item.policy_type=='living_allowance'
    assert LABELS['living_allowance']!=LABELS['elderly_service']


def test_reviewer_approval_cannot_override_scope_guards():
    paragraph=Paragraph(text='待遇面向全体户籍高龄老人。',sources=[1])
    review=Review.model_validate({'assessments':[{'paragraph':1,'policy_type':'living_allowance','supported':True,'addresses_question':True,'reason':'supported','quotes':[{'source_index':1,'span_ids':[1]}]}]})
    accepted,issues=evaluate_review(review,[paragraph],[{'index':1,'text':'100周岁及以上老人的高龄津贴标准调整为800元。'}])
    assert not accepted and issues==['unsupported_universal_scope']
