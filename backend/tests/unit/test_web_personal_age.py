from types import SimpleNamespace
import pytest
from app.services.chat.grounding import unsupported_ages,numeric_support_issues,evaluate_review,Review
from app.services.chat.citation import Paragraph
from app.services.chat.policy_checks import relevance_reason
from app.schemas.chat import PolicyQuestion,WebSource
from test_policy_graph import Model,hit,setup_retrieval,run

SOURCE='温州市基本公共服务标准（2023年版）。为80周岁以上老年人发放高龄津贴，每人每月不低于60元。具体认定评估办法及补贴标准由各地人民政府明确。'


@pytest.mark.parametrize('text,known,missing',[
 ('您提供的年龄为22岁，低于该文件80周岁以上的年龄要求。',{22},set()),
 ('您今年22岁，尚需核对当地条件。',{22},set()),
 ('您22岁，低于该文件的年龄要求。',{22},set()),
 ('您22岁以上即可领取。',{22},{22}),
 ('政策门槛为22至80周岁。',{22},{22}),
 ('您提供的年龄为22岁。',set(),{22}),
])
def test_personal_input_is_not_a_policy_numeric_anchor(text,known,missing):
 assert unsupported_ages(text,SOURCE,known)==missing


def test_personal_age_still_does_not_support_wrong_money_or_semantic_claim():
 p=Paragraph(text='您22岁，每人每月600元。',sources=[1])
 assert numeric_support_issues([p],[{'index':1,'text':SOURCE}],{22})==[{'paragraph':1,'type':'amount_not_in_evidence'}]
 review=Review.model_validate({'assessments':[{'paragraph':1,'policy_type':'high_age','supported':False,'addresses_question':True,'reason':'age_mismatch','quotes':[]}]})
 accepted,issues=evaluate_review(review,[p],[{'index':1,'text':SOURCE}],{22})
 assert not accepted and issues==['age_mismatch']


def test_high_age_search_rejects_childbearing_even_with_general_pension_words():
 body='温州市人民政府。满足高龄生育家庭需求，给予生育补贴。推进养老服务设施建设。'
 assert relevance_reason('温州市龙湾区高龄津贴申请', '温州市人民政府文件',body)=='specific_benefit_not_coincident'
 assert relevance_reason('温州市龙湾区高龄津贴申请','温州市基本公共服务标准',SOURCE) is None


def test_multiturn_wenzhou_answer_can_use_web_after_local_insufficiency(monkeypatch):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':'杭州市上城区养老服务补贴原文，90周岁及以上每人每月100元。'})])
 request=PolicyQuestion(question='龙湾区的',history=[{'role':'user','content':'我能申请养老补贴吗'},{'role':'assistant','content':'请问年龄、户籍和补贴类别？'},{'role':'user','content':'22岁温州市户籍'},{'role':'assistant','content':'请问补贴类别？'},{'role':'user','content':'高龄津贴'},{'role':'assistant','content':'请问温州市哪个区？'}])
 web=SimpleNamespace(configured=True,search=lambda query:[WebSource(title='温州市基本公共服务标准（2023年版）',url='https://wenzhou.gov.cn/policy',content=SOURCE,retrieved_at='2026-10-30T00:00:00Z')])
 model=Model({'supported':True,'needs_clarification':False,'query':'温州市龙湾区22岁户籍居民能否申请高龄津贴','needs_freshness':False},{'sufficient':False,'paragraphs':[]},{'sufficient':True,'paragraphs':[{'text':'您提供的年龄为22岁，低于这份温州市2023年文件所写80周岁以上的年龄要求；该文件的高龄津贴为每人每月不低于60元，具体标准由各地明确，尚不能确认龙湾区今日标准及个人最终资格。','sources':[2]}]})
 from app.agents.orchestrator import run_policy
 answer=run_policy(request,None,SimpleNamespace(ensure_configured=lambda:None),None,model,['general'],web=web)
 assert answer.status=='answered' and answer.web_status=='success'
 assert answer.citations[0].source_type=='web' and answer.answer_checks.status=='passed'
 assert '22岁' in answer.answer and '60元' in answer.answer and '100元' not in answer.answer
