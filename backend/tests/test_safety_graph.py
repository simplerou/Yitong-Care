from types import SimpleNamespace

import pytest

from app.agents.safety_orchestrator import run_safety
from app.schemas.retrieval import SearchHit
from app.schemas.safety import SafetyProfile, SafetyQuestion

DRAFT = {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
         'paragraphs': [{'text': '卫生间马桶旁和淋浴区应安装扶手，地面铺防滑垫，起夜路上加感应夜灯。',
                         'sources': [1], 'kind': 'environment'}]}


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
                query='老年人居家防跌倒 卫生间扶手 适老化改造', intent='environment', missing_fields=[],
                needs_freshness=False, possible_emergency=False, route='safety')
    base.update(updates)
    return base


def hit(index=1):
    text = '老年人居家防跌倒应优先处理通道、地面和照明，卫生间马桶旁与淋浴区安装扶手，扶手常见高度 70–80 cm。'
    return SearchHit(chunk_id=index, doc_id='safety', kb_id='general', doc_name='老年人跌倒干预技术指南', type='TXT',
                     source='本地上传', seq=index, start=0, end=len(text), chars=len(text), text=text,
                     score=.9, cos=.9, lexical_score=1.0)


def setup(monkeypatch, hits):
    from app.agents import safety_orchestrator
    calls = []

    def search(db, request, embedder, manager, allowed_kb_ids):
        calls.append((request, allowed_kb_ids))
        return SimpleNamespace(hits=list(hits), log_id='retrieval-1', vector_count=6)

    monkeypatch.setattr(safety_orchestrator.hybrid, 'search', search)
    return calls


def ask(monkeypatch, model, question, hits=None, profile=None, **kwargs):
    calls = setup(monkeypatch, [hit()] if hits is None else hits)
    result = run_safety(SafetyQuestion(question=question, profile=profile or SafetyProfile(), **kwargs), None,
                        SimpleNamespace(ensure_configured=lambda: None), None, model, ['safety'])
    return result, calls, model


def test_environment_answer_has_hazards_and_citations(monkeypatch):
    model = Model(understand(), DRAFT)
    result, calls, model = ask(monkeypatch, model, '卫生间装扶手大概多高')
    assert result.status == 'answered'
    assert [item.id for item in result.hazards] == ['bath_grab_bar']
    assert '【1】' in result.answer and '不构成医疗诊断' in result.answer
    assert [citation.index for citation in result.citations] == [1]
    assert result.answer_checks.status == 'passed'
    assert result.steps == ['understand', 'extract_hazards', 'assess_safety', 'retrieve', 'generate',
                            'validate', 'verify_grounding']
    assert len(model.calls) == 2 and len(model.review_calls) == 1


def test_fall_emergency_short_circuits(monkeypatch):
    model = Model(understand(intent='fall_event', possible_emergency=True))
    result, calls, model = ask(monkeypatch, model, '我爸摔倒了，髋部疼得站不起来')
    assert result.status == 'emergency' and result.urgency == 'L1'
    assert 'hip_fracture' in result.triage_rule_ids
    assert '120' in result.answer and '不要搬动' in result.answer
    assert not calls and 'retrieve' not in result.steps
    assert result.post_fall_advice and '先不要急着把人扶起来' in result.post_fall_advice


def test_rehab_prescription_returns_boundary(monkeypatch):
    model = Model(understand(intent='exercise'))
    result, calls, model = ask(monkeypatch, model, '给我一套康复训练处方')
    assert result.status == 'boundary' and result.reason == 'rehab_prescription_not_allowed'
    assert not calls and result.boundary


def test_construction_quote_returns_boundary(monkeypatch):
    model = Model(understand(intent='environment'))
    result, calls, model = ask(monkeypatch, model, '适老化改造大概多少钱')
    assert result.status == 'boundary' and result.reason == 'construction_quote_not_allowed'
    assert '报价' in result.answer


def test_clarification_skips_retrieval(monkeypatch):
    model = Model(understand(needs_clarification=True, query=None, clarification='请补充是哪个房间。'))
    result, calls, model = ask(monkeypatch, model, '家里要改造')
    assert result.status == 'clarification' and result.reason == 'missing_conditions'
    assert not calls and '请补充是哪个房间' in result.answer


def test_no_hits_keeps_risk_and_postfall_blocks(monkeypatch):
    model = Model(understand(intent='fall_event'))
    result, calls, model = ask(monkeypatch, model, '独居老人摔倒起不来', hits=[])
    assert result.status == 'insufficient' and result.reason == 'no_hits'
    assert '不要急着' in result.answer and '120' in result.answer


def test_rushing_to_lift_is_blocked(monkeypatch):
    unsafe = {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
              'paragraphs': [{'text': '赶紧扶起来，肯定就是骨折了。', 'sources': [1], 'kind': 'action'}]}
    model = Model(understand(intent='fall_event'), unsafe, unsafe)
    result, calls, model = ask(monkeypatch, model, '老人摔倒了怎么办')
    assert result.status == 'insufficient' and result.reason == 'unsafe_paragraph'
    assert result.citations == []
    assert '扶起来' not in result.answer


def test_invented_dimension_is_blocked(monkeypatch):
    unsafe = {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
              'paragraphs': [{'text': '扶手应装在 95 cm 的高度。', 'sources': [1], 'kind': 'environment'}]}
    model = Model(understand(), unsafe, unsafe)
    result, calls, model = ask(monkeypatch, model, '卫生间装扶手多高')
    assert result.status == 'insufficient'
    assert '95 cm' not in result.answer


def test_review_failure_never_releases_the_draft(monkeypatch):
    model = Model(understand(), DRAFT, review='fail')
    result, calls, model = ask(monkeypatch, model, '卫生间装扶手多高')
    assert result.status == 'insufficient' and result.reason == 'grounding_review_failed'
    assert '马桶旁和淋浴区应安装扶手' not in result.answer
    assert result.citations == []


def test_safety_metrics_are_request_scoped(monkeypatch):
    model = Model(understand(), DRAFT)
    result, calls, model = ask(monkeypatch, model, '卫生间装扶手多高')
    assert result.metrics.llm_calls == 3
    assert set(result.metrics.stage_ms) >= {'understand', 'extract_hazards', 'assess_safety', 'retrieve',
                                            'generate', 'validate', 'verify_grounding'}
