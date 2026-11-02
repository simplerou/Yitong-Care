from types import SimpleNamespace

import pytest

from app.agents.mind_orchestrator import run_mind
from app.schemas.mind import MindQuestion
from app.schemas.retrieval import SearchHit

DRAFT = {'sufficient': True, 'coverage': 'complete', 'missing_topics': [], 'paragraphs': [
    {'text': '听到你说老伴走了以后一直高兴不起来，这种空落落的感觉一定很难熬。', 'sources': [], 'kind': 'empathy'},
    {'text': '哀伤没有固定时间表，可以留一个固定时段想念，其他时间把注意力放回当下的小事。',
     'sources': [1], 'kind': 'advice'}]}
EMPATHY_ONLY = {'sufficient': True, 'coverage': 'partial', 'missing_topics': [], 'paragraphs': [
    {'text': '听到你这么说，我能感觉到你很累，也很孤单。', 'sources': [], 'kind': 'empathy'}]}


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
        assessments = []
        for item in payload['paragraphs']:
            if item.get('kind') == 'empathy':
                assessments.append({'paragraph': item['paragraph'], 'supported': True,
                                    'addresses_question': True, 'reason': 'supported', 'quotes': []})
            else:
                assessments.append({'paragraph': item['paragraph'], 'supported': True,
                                    'addresses_question': True, 'reason': 'supported',
                                    'quotes': [{'source_index': item['sources'][0],
                                                'text': evidence[item['sources'][0]][:40], 'span_ids': []}]})
        return {'assessments': assessments}


def understand(**updates):
    base = dict(supported=True, needs_clarification=False, clarification=None,
                query='丧亲哀伤 陪伴 老年人 心理', intent='grief', missing_fields=[],
                needs_freshness=False, possible_crisis=False, route='mind')
    base.update(updates)
    return base


def hit(index=1):
    text = '哀伤是失去亲人后的正常反应，可能反复出现想念与愧疚；哀伤没有固定时间表，可以留固定时段思念，其他时间把注意力放回当下。'
    return SearchHit(chunk_id=index, doc_id='mind', kb_id='general', doc_name='老年心理关怀指南', type='TXT',
                     source='本地上传', seq=index, start=0, end=len(text), chars=len(text), text=text,
                     score=.9, cos=.9, lexical_score=1.0)


def setup(monkeypatch, hits):
    from app.agents import mind_orchestrator
    calls = []

    def search(db, request, embedder, manager, allowed_kb_ids):
        calls.append((request, allowed_kb_ids))
        return SimpleNamespace(hits=list(hits), log_id='retrieval-1', vector_count=5)

    monkeypatch.setattr(mind_orchestrator.hybrid, 'search', search)
    return calls


def ask(monkeypatch, model, question, hits=None, **kwargs):
    calls = setup(monkeypatch, [hit()] if hits is None else hits)
    result = run_mind(MindQuestion(question=question, **kwargs), None,
                      SimpleNamespace(ensure_configured=lambda: None), None, model, ['mind'])
    return result, calls, model


def test_crisis_returns_fixed_protocol_without_retrieval(monkeypatch):
    model = Model(understand(intent='emotional_support', possible_crisis=True))
    result, calls, model = ask(monkeypatch, model, '我不想活了，活着没意思')
    assert result.status == 'crisis' and result.urgency == 'L1'
    assert '12356' in result.answer and '120' in result.answer
    assert '不要一个人扛' not in result.answer and '不需要一个人扛' in result.answer
    assert not calls and 'retrieve' not in result.steps
    assert result.crisis_notice and '你现在安全吗' in result.crisis_notice
    assert len(model.calls) == 1


def test_grief_answer_has_empathy_advice_and_citations(monkeypatch):
    model = Model(understand(), DRAFT)
    result, calls, model = ask(monkeypatch, model, '老伴走了以后，一直高兴不起来')
    assert result.status == 'answered' and result.urgency == 'L3'
    assert [item.kind for item in result.advice] == ['empathy', 'advice']
    assert '【1】' in result.answer and '不构成诊断' in result.answer
    assert [citation.index for citation in result.citations] == [1]
    assert result.answer_checks.status == 'passed'
    assert result.steps == ['understand', 'assess_mind', 'retrieve', 'generate', 'validate', 'verify_grounding']


def test_depression_screen_adds_safety_plan(monkeypatch):
    model = Model(understand(intent='emotional_support'), DRAFT)
    result, calls, model = ask(monkeypatch, model, '最近两周心情低落，什么都不想做')
    assert result.status == 'answered' and result.urgency == 'L2'
    assert result.screening and result.screening.positive is True
    assert any('12356' in step for step in result.safety_plan)
    assert '不是诊断' in result.answer
    assert '精神科' in result.answer or '心理科' in result.answer


def test_loneliness_gets_code_owned_tips(monkeypatch):
    model = Model(understand(intent='loneliness'), EMPATHY_ONLY)
    result, calls, model = ask(monkeypatch, model, '一个人住，没人说话')
    assert result.status == 'answered' and result.urgency == 'L3'
    assert '社区' in result.answer or '邻居' in result.answer


def test_therapy_request_returns_boundary(monkeypatch):
    model = Model(understand(intent='therapy_request'))
    result, calls, model = ask(monkeypatch, model, '给我一套治疗抑郁的方案')
    assert result.status == 'boundary' and result.reason == 'therapy_request_not_allowed'
    assert not calls and result.boundary


def test_medication_request_routes_to_medication_agent(monkeypatch):
    model = Model(understand(intent='medication_request'))
    result, calls, model = ask(monkeypatch, model, '安眠药吃几片合适')
    assert result.status == 'boundary' and result.reason == 'medication_request_not_allowed'
    assert result.route_suggestion is not None and result.route_suggestion.agent == 'medication'


def test_clarification_when_no_signals(monkeypatch):
    model = Model(understand(needs_clarification=True, query=None, clarification='这种状态大概持续多久了？'))
    result, calls, model = ask(monkeypatch, model, '我想找人聊聊')
    assert result.status == 'clarification' and result.reason == 'missing_conditions'
    assert not calls and '持续多久' in result.answer


def test_no_evidence_falls_back_to_supportive_answer(monkeypatch):
    model = Model(understand(intent='emotional_support'), EMPATHY_ONLY)
    result, calls, model = ask(monkeypatch, model, '最近心里空落落的', hits=[])
    assert result.status == 'answered'
    assert '我在' in result.answer or '听到你' in result.answer
    assert '不构成诊断' in result.answer
    assert result.citations == []


def test_toxic_positivity_is_blocked(monkeypatch):
    toxic = {'sufficient': True, 'coverage': 'complete', 'missing_topics': [], 'paragraphs': [
        {'text': '想开点，别想太多，比你惨的人多了。', 'sources': [], 'kind': 'empathy'}]}
    model = Model(understand(intent='emotional_support'), toxic, toxic)
    result, calls, model = ask(monkeypatch, model, '我很难过')
    assert '想开点' not in result.answer
    assert result.status in {'answered', 'insufficient'}


def test_method_details_are_blocked(monkeypatch):
    method = {'sufficient': True, 'coverage': 'complete', 'missing_topics': [], 'paragraphs': [
        {'text': '如果实在难受，可以试试跳楼以外的办法。', 'sources': [1], 'kind': 'advice'}]}
    model = Model(understand(intent='emotional_support'), method, method)
    result, calls, model = ask(monkeypatch, model, '我很难受')
    assert '跳楼' not in result.answer


def test_review_failure_does_not_release_advice(monkeypatch):
    model = Model(understand(), DRAFT, review='fail')
    result, calls, model = ask(monkeypatch, model, '老伴走了以后，一直高兴不起来')
    assert result.status in {'insufficient', 'answered'}
    assert '哀伤没有固定时间表' not in result.answer
    assert result.citations == []


def test_mind_metrics_are_request_scoped(monkeypatch):
    model = Model(understand(), DRAFT)
    result, calls, model = ask(monkeypatch, model, '老伴走了以后，一直高兴不起来')
    assert result.metrics.llm_calls == 3
    assert set(result.metrics.stage_ms) >= {'understand', 'assess_mind', 'retrieve', 'generate',
                                            'validate', 'verify_grounding'}
