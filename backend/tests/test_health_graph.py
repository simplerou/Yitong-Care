from types import SimpleNamespace

import pytest

from app.agents.health_orchestrator import run_health
from app.core.exceptions import BusinessError
from app.schemas.health import HealthProfile, HealthQuestion
from app.schemas.retrieval import SearchHit


class Model:
    model = 'test-qwen'

    def __init__(self, *responses, review=None):
        self.responses = list(responses)
        self.review = review
        self.calls = []
        self.review_calls = []

    def ensure_configured(self): pass

    def complete_json(self, system, payload, max_tokens=1800):
        self.calls.append(payload)
        return self.responses.pop(0)

    def review_json(self, system, payload):
        self.review_calls.append(payload)
        if self.review == 'fail': raise ValueError('unusable review')
        evidence = {item['index']: item['text'] for item in payload['evidence']}
        return {'assessments': [{'paragraph': item['paragraph'], 'supported': True,
                                 'addresses_question': True, 'reason': 'supported',
                                 'quotes': [{'source_index': item['sources'][0],
                                             'text': evidence[item['sources'][0]][:60], 'span_ids': []}]}
                                for item in payload['paragraphs']]}


def understand(**updates):
    base = dict(supported=True, needs_clarification=False, clarification=None, query='家庭血压判读',
                metric='blood_pressure', missing_fields=[], needs_freshness=False,
                possible_emergency=False, route='health', reported_value=None)
    base.update(updates)
    return base


def hit(index=1):
    return SearchHit(chunk_id=index, doc_id='health', kb_id='general', doc_name='高血压指南', type='TXT',
                     source='本地上传', seq=index, start=0, end=40, chars=40,
                     text='家庭自测血压≥135/85 mmHg视为偏高，应复测并记录。', score=.5, cos=.8, lexical_score=1.0)


def draft(text='本次测量 150/95 mmHg 属于偏高范围，建议复测并记录。', sources=None, sufficient=True):
    return {'sufficient': sufficient, 'coverage': 'complete', 'missing_topics': [],
            'paragraphs': [{'text': text, 'sources': sources or [1], 'kind': 'explain'}] if sufficient else []}


def setup(monkeypatch, hits):
    from app.agents import health_orchestrator
    calls = []

    def search(db, request, embedder, manager, allowed_kb_ids):
        calls.append((request, allowed_kb_ids))
        return SimpleNamespace(hits=hits, log_id='retrieval-1', vector_count=10)

    monkeypatch.setattr(health_orchestrator.hybrid, 'search', search)
    return calls


def ask(monkeypatch, model, question, hits=None, **kwargs):
    calls = setup(monkeypatch, hits if hits is not None else [hit()])
    result = run_health(HealthQuestion(question=question, **kwargs), None,
                        SimpleNamespace(ensure_configured=lambda: None), None, model, ['health'])
    return result, calls, model


def test_emergency_short_circuits_retrieval_and_uses_no_generation(monkeypatch):
    model = Model(understand(possible_emergency=True))
    result, calls, model = ask(monkeypatch, model, '我爸胸口压得慌，出冷汗十几分钟了')
    assert result.status == 'emergency'
    assert result.urgency == 'L1' and result.required_action == 'call_120'
    assert not calls
    assert '120' in result.answer and '建议近期到门诊复查' not in result.answer
    assert result.steps == ['understand', 'assess_vitals', 'triage', 'emergency']
    assert len(model.calls) == 1
    assert 'emergency' in result.metrics.stage_ms


def test_emergency_text_does_not_depend_on_the_model(monkeypatch):
    class BrokenModel(Model):
        def complete_json(self, *args, **kwargs):
            raise BusinessError('模型不可用', 502)

    model = BrokenModel()
    calls = setup(monkeypatch, [])
    with pytest.raises(BusinessError):
        run_health(HealthQuestion(question='胸痛十几分钟了'), None,
                   SimpleNamespace(ensure_configured=lambda: None), None, model, ['health'])
    # Understand is the only model call; the emergency copy itself is produced by code.
    from app.services.health import checks, triage as triage_rules, vitals
    assessment = vitals.assess('胸痛十几分钟了', [], [], HealthProfile())
    tri = triage_rules.triage_of(assessment, '胸痛十几分钟了', HealthProfile())
    assert '120' in checks.emergency_text(tri, assessment)


def test_clarification_skips_retrieval(monkeypatch):
    model = Model(understand(needs_clarification=True, clarification='请补充测量到的血压数值。', query=None))
    result, calls, model = ask(monkeypatch, model, '我的血压高吗', hits=[])
    assert result.status == 'clarification' and result.reason == 'missing_conditions'
    assert not calls
    assert '请补充测量到的血压数值' in result.answer
    assert result.steps == ['understand', 'assess_vitals', 'triage', 'clarify']
    assert len(model.calls) == 1


def test_out_of_scope_returns_route_suggestion(monkeypatch):
    model = Model(understand(supported=False, needs_clarification=True, query=None,
                             clarification='用药剂量问题请咨询用药管家。', route='medication'))
    result, calls, model = ask(monkeypatch, model, '这药能吃两片吗', hits=[])
    assert result.status == 'clarification' and result.reason == 'outside_scope'
    assert result.route_suggestion is not None and result.route_suggestion.agent == 'medication'
    assert not calls


def test_answered_answer_has_assessment_referral_and_citations(monkeypatch):
    model = Model(understand(), draft())
    result, calls, model = ask(monkeypatch, model, '早上量的 150/95')
    assert result.status == 'answered'
    assert '1级高血压' in result.answer and '判读表 cn-bp' in result.answer
    assert '【1】' in result.answer
    assert '建议近期到门诊复查' in result.answer
    assert '不构成诊断或处方' in result.answer
    assert [citation.index for citation in result.citations] == [1]
    assert result.citations[0].hit.chunk_id == 1
    assert result.coverage == 'complete'
    assert result.answer_checks.status == 'passed'
    assert result.steps == ['understand', 'assess_vitals', 'triage', 'retrieve', 'generate', 'validate', 'verify_grounding']
    assert calls[0][1] == ['health']
    assert len(model.calls) == 2 and len(model.review_calls) == 1


def test_no_hits_returns_assessment_and_emergency_checklist(monkeypatch):
    model = Model(understand())
    result, calls, model = ask(monkeypatch, model, '血压多少算正常', hits=[])
    assert result.status == 'insufficient' and result.reason == 'no_hits'
    assert '120' in result.answer and '不构成诊断或处方' in result.answer
    assert len(model.calls) == 1


def test_unsafe_draft_is_blocked_without_citing_it(monkeypatch):
    model = Model(understand(), draft('可以把氨氯地平加到两片。'), draft('可以把氨氯地平加到两片。'))
    result, calls, model = ask(monkeypatch, model, '早上 150/95，能加药吗')
    assert result.status == 'insufficient'
    assert result.reason == 'unsafe_paragraph'
    assert result.citations == []
    assert '两片' not in result.answer
    assert len(model.calls) == 3


def test_invented_numbers_are_blocked(monkeypatch):
    model = Model(understand(), draft('建议把血压控制到 120/70 mmHg 以下。'), draft('建议把血压控制到 120/70 mmHg 以下。'))
    result, calls, model = ask(monkeypatch, model, '早上 150/95')
    assert result.status == 'insufficient'
    assert result.reason == 'unsupported_number'
    assert result.citations == []


def test_review_failure_never_releases_the_draft(monkeypatch):
    model = Model(understand(), draft(), review='fail')
    result, calls, model = ask(monkeypatch, model, '早上 150/95')
    assert result.status == 'insufficient' and result.reason == 'grounding_review_failed'
    assert '本次测量 150/95' not in result.answer.split('判读依据')[-1]
    assert '不构成诊断或处方' in result.answer
    assert result.citations == []


def test_implausible_value_leads_to_clarification_not_classification(monkeypatch):
    model = Model(understand(needs_clarification=False))
    result, calls, model = ask(monkeypatch, model, '血压 900/60', hits=[])
    assert result.status == 'clarification'
    assert result.vitals_assessment is not None
    assert result.vitals_assessment.readings[0].category_code == 'unverified'
    assert '未参与' in result.answer
    assert not calls


def test_llm_metrics_are_request_scoped(monkeypatch):
    model = Model(understand(), draft())
    result, calls, model = ask(monkeypatch, model, '早上 150/95')
    assert result.metrics.llm_calls == 3
    assert result.metrics.llm_failures == 0
    assert set(result.metrics.stage_ms) >= {'understand', 'assess_vitals', 'triage', 'retrieve', 'generate',
                                            'validate', 'verify_grounding'}
