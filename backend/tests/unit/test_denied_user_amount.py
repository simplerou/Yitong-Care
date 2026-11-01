import pytest
from app.services.chat.citation import Paragraph
from app.services.chat.grounding import remove_denied_user_amount,numeric_support_issues
from app.schemas.chat import PolicyQuestion
from test_policy_graph import Model,decision,hit,setup_retrieval,run

SOURCE='上城区户籍90周岁及以上高龄老人的养老服务补贴为每人每月100元。'
QUESTION='上城区户籍90岁老人的高龄老年人养老服务补贴，是不是按杭民发〔2024〕142号每月领9999元？'
EVIDENCE=[{'index':1,'text':SOURCE}]


@pytest.mark.parametrize('text',[
 '不是9999元，原文为每人每月100元。',
 '并非每月领取9999元。根据该文件，对应标准为每人每月100元。',
 '不是每人每月9999元，而是每人每月100元。',
 '根据该文件，标准为每人每月100元，而非9999元。',
])
def test_remove_only_denied_user_number_keep_supported_correction(text):
 paragraph=Paragraph(text=text,sources=[1])
 fixed=remove_denied_user_amount(paragraph,EVIDENCE,QUESTION)
 assert '9999' not in fixed.text and '100元' in fixed.text
 assert fixed.sources==[1] and numeric_support_issues([fixed],EVIDENCE)==[]


@pytest.mark.parametrize('text,question',[
 ('是的，每月领取9999元。',QUESTION),
 ('不是9999元，标准为每月400元。',QUESTION),
 ('不是9999元。',QUESTION),
 ('不是8888元，标准为每月100元。',QUESTION),
 ('不是9999元，标准为每月100元。','养老补贴标准是多少？'),
 ('不是9999元，85岁以上每月100元。',QUESTION),
])
def test_do_not_silently_remove_positive_unknown_or_unsupported_claims(text,question):
 paragraph=Paragraph(text=text,sources=[1])
 assert remove_denied_user_amount(paragraph,EVIDENCE,question)==paragraph


def test_full_workflow_reviews_sanitized_correction_and_preserves_semantic_veto(monkeypatch):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':SOURCE})])
 draft={'sufficient':True,'paragraphs':[{'text':'不是9999元，原文为每人每月100元。','sources':[1]}]}
 model=Model(decision(),draft)
 model.review_response={'assessments':[{'paragraph':1,'policy_type':'elderly_service','supported':False,'addresses_question':True,'reason':'missing_conditions','quotes':[]}]}
 answer=run(model,PolicyQuestion(question=QUESTION))
 assert '9999' not in model.review_calls[0]['paragraphs'][0]['text']
 assert answer.status=='insufficient' and not answer.citations


def test_failure_records_exact_numeric_issue_and_supplies_targeted_retry(monkeypatch):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':SOURCE})])
 draft={'sufficient':True,'paragraphs':[{'text':'是的，每月9999元。','sources':[1]}]}
 model=Model(decision(),draft,draft)
 answer=run(model,PolicyQuestion(question=QUESTION))
 assert answer.answer_checks.issues==['generation_amount_not_in_evidence:paragraph_1']
 assert model.calls[2]['numeric_retry']['issues'][0]['type']=='amount_not_in_evidence'
 assert not answer.citations


def test_real_t06_middle_denial_keeps_following_conditions_and_passes_full_workflow(monkeypatch):
 import json
 from pathlib import Path
 fixture=json.loads((Path(__file__).parents[1]/'fixtures/policy_t06_denial_middle.json').read_text())
 for draft in fixture['drafts']:
  paragraph=Paragraph.model_validate(draft['paragraphs'][0])
  original_tail=paragraph.text.split('9999元。',1)[1]
  fixed=remove_denied_user_amount(paragraph,fixture['evidence'],fixture['question'])
  assert '9999元' not in fixed.text and '100元' in fixed.text
  assert fixed.text.endswith(original_tail) and fixed.sources==paragraph.sources
  assert numeric_support_issues([fixed],fixture['evidence'])==[]
 hits=[hit(i).model_copy(update={'text':item['text']}) for i,item in enumerate(fixture['evidence'],1)]
 setup_retrieval(monkeypatch,hits)
 model=Model(decision(),fixture['drafts'][0])
 answer=run(model,PolicyQuestion(question=fixture['question']))
 assert answer.status=='answered' and '100元' in answer.answer and '9999' not in answer.answer
 assert answer.answer_checks.status=='passed' and len(model.calls)==2
 assert answer.citations and '该标准适用于' in answer.answer


def test_middle_denial_does_not_drop_subsequent_unsupported_claim():
 paragraph=Paragraph(text='每月100元，而非9999元。另加每月888元。',sources=[1])
 assert remove_denied_user_amount(paragraph,EVIDENCE,QUESTION)==paragraph
