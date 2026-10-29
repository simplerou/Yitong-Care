import json
from pathlib import Path
import pytest
from app.evaluation.policy import load_dataset, check_answer, write_report, DATASET_PATH
from app.schemas.chat import PolicyAnswer, Citation, AnswerChecks
from test_policy_graph import hit


def answer(text='每月40元。【1】',index=1):
    source=hit().model_copy(update={'text':'80至89周岁每月40元。'})
    return PolicyAnswer(status='answered',answer=text,citations=[Citation(index=index,hit=source)],retrieved_hits=[source],
        model='test-model',knowledge_scope=['general'],steps=['retrieve','verify_grounding'],answer_checks=AnswerChecks(status='passed',checked_paragraphs=1,accepted_paragraphs=1))


def test_dataset_quotes_and_ids_are_valid():
    data,cases=load_dataset()
    assert len(cases)==18 and len({c.id for c in cases})==18
    assert sum(c.mode=='web' for c in cases)==2
    assert data['reference']['current_validity']=='not_verified'
    assert next(c for c in cases if c.id=='P15').turns[-1]=='那90岁呢？'


def test_wrong_amount_fails_fixed_answer_anchor():
    _,cases=load_dataset();case=next(c for c in cases if c.id=='P02')
    checks=check_answer(case,answer('每月400元。【1】'))
    assert any(not c['passed'] and c['name']=='answer_anchor_1' for c in checks)


def test_forged_marker_and_source_position_fail():
    _,cases=load_dataset();case=next(c for c in cases if c.id=='P02')
    checks=check_answer(case,answer('每月40元。【99】',99))
    assert any(c['name']=='citation_source_99' and not c['passed'] for c in checks)
    checks=check_answer(case,answer('每月40元。【2】'))
    assert any(c['name']=='citation_markers_match' and not c['passed'] for c in checks)


def test_latest_question_requires_actual_web_attempt():
    _,cases=load_dataset();case=next(c for c in cases if c.id=='W01')
    checks=check_answer(case,answer())
    assert any(c['name']=='web_attempted' and not c['passed'] for c in checks)


def test_changed_reference_is_rejected(tmp_path):
    payload=json.loads(DATASET_PATH.read_text())
    (tmp_path/'cases.json').write_text(json.dumps(payload))
    (tmp_path/'reference.txt').write_text('not the reference')
    with pytest.raises(ValueError,match='hash mismatch'): load_dataset(tmp_path/'cases.json')


def test_report_never_treats_not_run_as_failure(tmp_path):
    report={'status':'blocked','dataset_version':'test','mode':'live_local_only','blocking_reason':'数据库预检失败',
        'results':[{'id':'P01','topic':'概览','automatic_status':'not_run','manual_status':'not_run','manual_checks':['核对原文'],'turns':[]}]}
    path=write_report(report,tmp_path)
    text=(path/'report.md').read_text()
    assert 'not_run' in text and '不等于政策事实正确' in text
    assert json.loads((path/'report.json').read_text())['status']=='blocked'


def test_equivalent_nonduplication_wording_does_not_false_fail():
    _,cases=load_dataset()
    for case_id,text in [('P12','不得重复享受。'),('P13','差额发放，不再重复享受。')]:
        case=next(c for c in cases if c.id==case_id)
        checks=check_answer(case,answer(text+'【1】'))
        assert all(c['passed'] for c in checks if c['name'].startswith('answer_anchor'))
