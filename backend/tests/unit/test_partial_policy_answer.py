from types import SimpleNamespace
from app.schemas.chat import PolicyQuestion
from app.agents.orchestrator import run_policy
from app.services.chat.dialogue_state import build_dialogue
from test_policy_graph import Model,hit,setup_retrieval

SOURCE='温州市长期护理保险资料：居家护理服务包括生活照护和医疗护理。具体支付范围以相关目录和待遇条件为准。'
STATE=build_dialogue(['22岁温州市户籍','龙湾区的','长期护理保险','服务项目'])


def execute(model):
 return run_policy(PolicyQuestion(question='服务项目',dialogue_state=STATE),None,SimpleNamespace(ensure_configured=lambda:None),None,model,['general'])


def test_partial_candidate_is_reviewed_and_returned_with_explicit_gap(monkeypatch):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':SOURCE})])
 model=Model({'supported':True,'needs_clarification':False,'query':'温州市龙湾区长期护理保险服务项目'}, {'sufficient':False,'coverage':'partial','missing_topics':['local_service_catalog'],'paragraphs':[{'text':'所引温州资料仅说明居家护理包括生活照护和医疗护理，具体支付范围须核对目录与条件。','sources':[1]}]})
 answer=execute(model)
 assert answer.status=='answered' and answer.coverage=='partial' and answer.citations
 assert answer.missing_topics==['local_service_catalog'] and answer.answer_checks.status=='passed'
 assert '仅回答已有原文支持的部分' in answer.answer and answer.general_info
 assert len(model.review_calls)==1


def test_no_source_has_specific_gap_and_separate_concept_help(monkeypatch):
 setup_retrieval(monkeypatch,[])
 answer=execute(Model({'supported':True,'needs_clarification':False,'query':'温州市龙湾区长期护理保险服务项目'}))
 assert answer.status=='insufficient' and answer.coverage=='none'
 assert answer.missing_topics==['local_service_catalog'] and '服务目录' in answer.answer
 assert '可明确具体补贴类别' not in answer.answer and answer.general_info and not answer.citations
 assert all('龙湾区可支付' not in text for text in answer.general_info)


def test_partial_draft_does_not_bypass_semantic_rejection(monkeypatch):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':SOURCE})])
 model=Model({'supported':True,'needs_clarification':False,'query':'温州市长护险服务项目'},{'sufficient':True,'coverage':'partial','paragraphs':[{'text':'龙湾区居民可直接享受这些服务。','sources':[1]}]})
 model.review_response={'assessments':[{'paragraph':1,'policy_type':'long_term_care','supported':False,'addresses_question':True,'reason':'missing_conditions','quotes':[]}]}
 answer=execute(model)
 assert answer.status=='insufficient' and not answer.citations and not answer.general_info


def test_partial_money_errors_still_blocked_not_replaced_by_generic_intro(monkeypatch):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':SOURCE})])
 bad={'sufficient':True,'coverage':'partial','paragraphs':[{'text':'居家护理每月9999元。','sources':[1]}]}
 model=Model({'supported':True,'needs_clarification':False,'query':'温州市长期护理保险服务项目'},bad,bad)
 answer=execute(model)
 assert answer.reason=='unsupported_numeric_expansion' and not answer.general_info and not answer.citations


def test_complete_supported_answer_needs_no_general_intro(monkeypatch):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':SOURCE})])
 model=Model({'supported':True,'needs_clarification':False,'query':'温州市长期护理保险服务项目'},{'sufficient':True,'paragraphs':[{'text':'所引条款写明居家护理服务包括生活照护和医疗护理。','sources':[1]}]})
 answer=execute(model)
 assert answer.status=='answered' and answer.coverage=='complete' and not answer.general_info
