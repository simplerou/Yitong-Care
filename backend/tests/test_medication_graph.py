from types import SimpleNamespace

import pytest

from app.agents.medication_orchestrator import run_medication
from app.core.exceptions import BusinessError
from app.schemas.medication import MedicationQuestion
from app.schemas.retrieval import SearchHit

DRAFT = {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
         'paragraphs': [{'text': '华法林与阿司匹林同用会增加出血风险，应让医生或药师核对。', 'sources': [1], 'kind': 'caution'}]}


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
        return {'assessments': [{'paragraph': item['paragraph'], 'supported': True, 'addresses_question': True,
                                 'reason': 'supported',
                                 'quotes': [{'source_index': item['sources'][0],
                                             'text': evidence[item['sources'][0]][:40], 'span_ids': []}]}
                                for item in payload['paragraphs']]}


def understand(**updates):
    base = dict(supported=True, needs_clarification=False, clarification=None,
                query='华法林与阿司匹林同用的出血风险', topic='interaction', drugs=[],
                missing_fields=[], needs_freshness=False, possible_emergency=False, route='medication')
    base.update(updates)
    return base


def hit(index=1):
    text = '华法林与阿司匹林合用会增加出血风险，需由医生评估。抗凝药使用者出现黑便应及时就医。'
    return SearchHit(chunk_id=index, doc_id='med', kb_id='general', doc_name='老年人合理用药手册', type='TXT',
                     source='本地上传', seq=index, start=0, end=len(text), chars=len(text), text=text,
                     score=.9, cos=.9, lexical_score=1.0)


def setup(monkeypatch, hits):
    from app.agents import medication_orchestrator
    calls = []

    def search(db, request, embedder, manager, allowed_kb_ids):
        calls.append((request, allowed_kb_ids))
        return SimpleNamespace(hits=list(hits), log_id='retrieval-1', vector_count=8)

    monkeypatch.setattr(medication_orchestrator.hybrid, 'search', search)
    return calls


def ask(monkeypatch, model, question, hits=None, **kwargs):
    calls = setup(monkeypatch, [hit()] if hits is None else hits)
    result = run_medication(MedicationQuestion(question=question, **kwargs), None,
                            SimpleNamespace(ensure_configured=lambda: None), None, model, ['med'])
    return result, calls, model


def test_interaction_answer_carries_rule_findings_and_citations(monkeypatch):
    model = Model(understand(), DRAFT)
    result, calls, model = ask(monkeypatch, model, '华法林和阿司匹林一起吃要紧吗')
    assert result.status == 'answered' and result.urgency == 'L3'
    assert [item.id for item in result.interactions] == ['anticoagulant_antiplatelet']
    assert '需尽快核对' in result.answer and '华法林' in result.answer
    assert '【1】' in result.answer and '不构成处方' in result.answer
    assert [citation.index for citation in result.citations] == [1]
    assert result.citations[0].hit.chunk_id == 1
    assert result.answer_checks.status == 'passed'
    assert result.steps == ['understand', 'extract_medications', 'screen_safety', 'retrieve', 'generate',
                            'validate', 'verify_grounding']
    assert len(model.calls) == 2 and len(model.review_calls) == 1
    assert calls[0][1] == ['med']


def test_dose_change_request_returns_boundary_without_retrieval(monkeypatch):
    model = Model(understand(topic='dose_change'))
    result, calls, model = ask(monkeypatch, model, '能把氨氯地平加到两片吗')
    assert result.status == 'boundary' and result.reason == 'dose_change_not_allowed'
    assert not calls
    assert '我不能提供加量' in result.answer
    assert '两片' not in result.answer
    assert result.boundary and '加量' in result.boundary
    assert len(model.calls) == 1


def test_stop_request_uses_the_stop_boundary(monkeypatch):
    model = Model(understand(topic='timing'))
    result, calls, model = ask(monkeypatch, model, '血压正常了想把降压药停掉')
    assert result.status == 'boundary' and result.reason == 'stop_or_switch_not_allowed'
    assert '是否停药或换药需要医生' in result.answer
    assert not calls


def test_emergency_short_circuits_before_retrieval(monkeypatch):
    model = Model(understand(topic='adverse_reaction', possible_emergency=True))
    result, calls, model = ask(monkeypatch, model, '吃了阿莫西林后起疹子，喘不上气')
    assert result.status == 'emergency' and result.urgency == 'L1' and result.required_action == 'call_120'
    assert '120' in result.answer and '带上所有正在服用的药物' in result.answer
    assert not calls and 'retrieve' not in result.steps
    assert model.calls and len(model.calls) == 1


def test_clarification_when_only_one_drug_is_known(monkeypatch):
    model = Model(understand(needs_clarification=True, query=None,
                             clarification='请补充另一种药的名称。'))
    result, calls, model = ask(monkeypatch, model, '这个药能一起吃吗')
    assert result.status == 'clarification' and result.reason == 'missing_conditions'
    assert not calls
    assert '请补充另一种药' in result.answer


def test_missed_dose_answer_includes_deterministic_advice(monkeypatch):
    model = Model(understand(topic='missed_dose', query='二甲双胍漏服怎么处理'), DRAFT)
    result, calls, model = ask(monkeypatch, model, '二甲双胍忘了吃怎么办')
    assert result.status == 'answered'
    assert result.missed_dose_advice and '双倍剂量' in result.missed_dose_advice
    assert '补服' in result.answer


def test_special_missed_dose_defers_to_doctor(monkeypatch):
    model = Model(understand(topic='missed_dose', query='华法林漏服怎么处理'), DRAFT)
    result, calls, model = ask(monkeypatch, model, '华法林忘记吃了怎么办')
    assert result.missed_dose_advice and '不要自行补服' in result.missed_dose_advice


def test_no_hits_keeps_interaction_block_and_emergency_copy(monkeypatch):
    model = Model(understand())
    result, calls, model = ask(monkeypatch, model, '华法林和阿司匹林', hits=[])
    assert result.status == 'insufficient' and result.reason == 'no_hits'
    assert [item.id for item in result.interactions] == ['anticoagulant_antiplatelet']
    assert '120' in result.answer and '不构成处方' in result.answer


def test_dose_number_in_draft_is_blocked(monkeypatch):
    unsafe = {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
              'paragraphs': [{'text': '建议每天服用 2 片，可以一起吃。', 'sources': [1], 'kind': 'caution'}]}
    model = Model(understand(), unsafe, unsafe)
    result, calls, model = ask(monkeypatch, model, '华法林和阿司匹林')
    assert result.status == 'insufficient'
    assert result.reason == 'unsafe_paragraph'
    assert result.citations == []
    assert '2 片' not in result.answer


def test_interaction_assertion_in_draft_is_blocked(monkeypatch):
    unsafe = {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
              'paragraphs': [{'text': '这两种药可以一起吃，没有相互作用。', 'sources': [1], 'kind': 'caution'}]}
    model = Model(understand(), unsafe, unsafe)
    result, calls, model = ask(monkeypatch, model, '华法林和阿司匹林')
    assert result.status == 'insufficient'
    assert '可以一起吃' not in result.answer


def test_review_failure_never_releases_the_draft(monkeypatch):
    model = Model(understand(), DRAFT, review='fail')
    result, calls, model = ask(monkeypatch, model, '华法林和阿司匹林')
    assert result.status == 'insufficient' and result.reason == 'grounding_review_failed'
    assert '华法林与阿司匹林同用会增加出血风险，应让医生或药师核对。' not in result.answer
    assert result.citations == []


def test_medication_metrics_are_request_scoped(monkeypatch):
    model = Model(understand(), DRAFT)
    result, calls, model = ask(monkeypatch, model, '华法林和阿司匹林')
    assert result.metrics.llm_calls == 3
    assert result.metrics.llm_failures == 0
    assert set(result.metrics.stage_ms) >= {'understand', 'extract_medications', 'screen_safety', 'retrieve',
                                            'generate', 'validate', 'verify_grounding'}
