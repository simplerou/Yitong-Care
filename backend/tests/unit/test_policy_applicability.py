from app.schemas.chat import PolicyQuestion
from test_policy_graph import Model,hit,setup_retrieval,run

QUESTION='宁波市户籍的老人，可以直接按杭民发〔2024〕142号中上城区的标准领取吗？'
SOURCE='养老服务补贴对象为本市户籍高龄老年人。上城区、拱墅区、西湖区、滨江区、钱塘区、西湖风景名胜区户籍，90周岁及以上每人每月100元。'


def test_scope_explanation_reaches_grounded_answer_without_claiming_ningbo_benefits(monkeypatch):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':SOURCE})])
 model=Model({'supported':True,'needs_clarification':True,'clarification':'请先选择本地政策还是异地申领。','query':None},{'sufficient':True,'paragraphs':[{'text':'仅凭所引条款，不能认定宁波市户籍老人可以直接按上城区标准领取。该条款要求本市户籍并列出上城区等适用地区，仍需核对宁波当地相关政策及条件。','sources':[1]}]})
 answer=run(model,PolicyQuestion(question=QUESTION))
 assert answer.status=='answered' and answer.citations and answer.answer_checks.status=='passed'
 assert '不能认定' in answer.answer and len(model.calls)==2
 assert '宁波' in model.calls[1]['user_question']


def test_cross_region_entitlement_still_subject_to_semantic_veto(monkeypatch):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':SOURCE})])
 model=Model({'supported':True,'needs_clarification':False,'query':QUESTION},{'sufficient':True,'paragraphs':[{'text':'宁波市户籍老人可以直接按上城区标准领取。','sources':[1]}]})
 model.review_response={'assessments':[{'paragraph':1,'policy_type':'elderly_service','supported':False,'addresses_question':True,'reason':'region_mismatch','quotes':[]}]}
 answer=run(model,PolicyQuestion(question=QUESTION))
 assert answer.status=='insufficient' and not answer.citations
 assert 'region_mismatch' in answer.answer_checks.issues
