import pytest
from app.services.chat.citation import Paragraph
from app.services.chat.grounding import unsupported_ages,numeric_support_issues,evaluate_review,Review
from app.schemas.chat import PolicyQuestion
from test_policy_graph import Model,decision,hit,setup_retrieval,run

SOURCE='上城区户籍高龄老人，80至89周岁的每人每月40元；90周岁及以上的每人每月100元。'


@pytest.mark.parametrize('text,user,missing',[
 ('您问的85岁属于80至89周岁档。',{85},set()),
 ('您问的85岁属于80至89周岁档。',set(),{85}),
 ('您问的79岁属于80至89周岁档。',{79},{79}),
 ('政策规定85岁以上每月40元。',{85},{85}),
 ('政策规定85至89周岁每月40元。',{85},{85}),
 ('政策规定年满85岁每月40元。',{85},{85}),
 ('95岁老人应核对90周岁及以上档。',{95},set()),
])
def test_only_user_age_membership_is_allowed(text,user,missing):
 assert unsupported_ages(text,SOURCE,user)==missing


def test_unrelated_digits_and_reversed_ranges_are_not_age_intervals():
 for source in ['80元至89元。','89至80周岁。','年龄资料不足。']:
  assert unsupported_ages('您问的85岁。',source,{85})=={85}


def test_money_guard_is_not_relaxed():
 paragraph=Paragraph(text='您问的85岁属于80至89周岁，每月400元。',sources=[1])
 assert numeric_support_issues([paragraph],[{'index':1,'text':SOURCE}],{85})==[{'paragraph':1,'type':'amount_not_in_evidence'}]


def review(supported=True,reason='supported'):
 return Review.model_validate({'assessments':[{'paragraph':1,'policy_type':'elderly_service','supported':supported,'addresses_question':True,'reason':reason,'quotes':[{'source_index':1,'text':SOURCE}]}]})


def test_quote_check_accepts_real_interval_and_keeps_semantic_veto():
 paragraphs=[Paragraph(text='您问的85岁属于80至89周岁，上城区户籍每人每月40元。',sources=[1])]
 evidence=[{'index':1,'text':SOURCE}]
 accepted,issues=evaluate_review(review(),paragraphs,evidence,user_ages={85})
 assert list(accepted)==[1] and issues==[]
 accepted,issues=evaluate_review(review(False,'age_mismatch'),paragraphs,evidence,user_ages={85})
 assert accepted=={} and issues==['age_mismatch']


def test_t02_generation_validation_and_review_share_interval_rules(monkeypatch):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':SOURCE})])
 model=Model(decision(),{'sufficient':True,'paragraphs':[{'text':'您问的85岁属于80至89周岁，上城区户籍高龄老人的养老服务补贴为每人每月40元。','sources':[1]}]})
 answer=run(model,PolicyQuestion(question='只根据杭民发〔2024〕142号，上城区户籍85岁老人的高龄老年人养老服务补贴标准是多少？'))
 assert answer.status=='answered' and '40元' in answer.answer and answer.citations
 assert answer.answer_checks.status=='passed' and len(model.calls)==2
 assert model.review_calls[0]['user_provided_ages']==[85]


def test_t03_full_answer_changes_85_to_90_and_40_to_100(monkeypatch):
 from app.schemas.chat import ChatTurn
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':SOURCE})])
 request=PolicyQuestion(question='那90岁呢？',history=[ChatTurn(role='user',content='只根据杭民发〔2024〕142号，上城区户籍85岁老人的高龄老年人养老服务补贴标准是多少？'),ChatTurn(role='assistant',content='对应80至89周岁，每人每月40元。')])
 model=Model(dict(supported=True,needs_clarification=True,clarification='请问你咨询的是什么地方的？',query=None),{'sufficient':True,'paragraphs':[{'text':'根据该文件，上城区户籍90周岁及以上高龄老人的养老服务补贴为每人每月100元。','sources':[1]}]})
 answer=run(model,request)
 assert answer.status=='answered' and '100元' in answer.answer and '40元' not in answer.answer
 assert '上城区户籍90岁' in model.calls[1]['user_question']
 assert answer.citations and answer.answer_checks.status=='passed'


def test_t06_repairs_repeated_false_amount_without_weakening_guard(monkeypatch):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':SOURCE})])
 question='上城区户籍90岁老人的高龄老年人养老服务补贴，是不是按杭民发〔2024〕142号每月领取9999元？'
 bad={'sufficient':True,'paragraphs':[{'text':'不是9999元，原文为每人每月100元。','sources':[1]}]}
 good={'sufficient':True,'paragraphs':[{'text':'不是。根据该文件，上城区户籍90周岁及以上高龄老人的养老服务补贴为每人每月100元。','sources':[1]}]}
 model=Model(dict(supported=True,needs_clarification=True,clarification='请确认是否为上城区户籍？',query=None),bad,good)
 answer=run(model,PolicyQuestion(question=question))
 assert answer.status=='answered' and '100元' in answer.answer and '9999' not in answer.answer
 assert len(model.calls)==2 and answer.citations and answer.answer_checks.status=='passed'


def test_t06_false_amount_still_blocked_when_model_does_not_repair(monkeypatch):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':SOURCE})])
 question='上城区户籍90岁老人的高龄老年人养老服务补贴，是不是按杭民发〔2024〕142号每月领取9999元？'
 bad={'sufficient':True,'paragraphs':[{'text':'是的，每人每月9999元。','sources':[1]}]}
 model=Model(decision(),bad,bad)
 answer=run(model,PolicyQuestion(question=question))
 assert answer.status=='insufficient' and answer.reason=='unsupported_numeric_expansion'
 assert not answer.citations and not model.review_calls
