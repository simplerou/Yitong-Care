from types import SimpleNamespace

import pytest

from app.agents.diet_orchestrator import run_diet
from app.schemas.diet import DietProfile, DietQuestion
from app.schemas.retrieval import SearchHit

DRAFT = {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
         'paragraphs': [{'text': '早餐用杂粮粥搭配鸡蛋和焯拌蔬菜，主食粗细搭配利于血压和血糖控制。',
                         'sources': [1], 'kind': 'meal'}]}


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
                query='老年人高血压一日三餐 控盐 膳食搭配', intent='meal_plan', foods=[],
                missing_fields=[], needs_freshness=False, possible_emergency=False, route='diet')
    base.update(updates)
    return base


def hit(index=1):
    text = '老年人膳食应食物多样，主食粗细搭配，每天摄入优质蛋白，控制食盐用量，多吃新鲜蔬菜水果。'
    return SearchHit(chunk_id=index, doc_id='diet', kb_id='general', doc_name='中国老年人膳食指南', type='TXT',
                     source='本地上传', seq=index, start=0, end=len(text), chars=len(text), text=text,
                     score=.9, cos=.9, lexical_score=1.0)


def setup(monkeypatch, hits):
    from app.agents import diet_orchestrator
    calls = []

    def search(db, request, embedder, manager, allowed_kb_ids):
        calls.append((request, allowed_kb_ids))
        return SimpleNamespace(hits=list(hits), log_id='retrieval-1', vector_count=7)

    monkeypatch.setattr(diet_orchestrator.hybrid, 'search', search)
    return calls


def ask(monkeypatch, model, question, hits=None, profile=None, **kwargs):
    calls = setup(monkeypatch, [hit()] if hits is None else hits)
    result = run_diet(DietQuestion(question=question, profile=profile or DietProfile(), **kwargs), None,
                      SimpleNamespace(ensure_configured=lambda: None), None, model, ['diet'])
    return result, calls, model


def test_meal_plan_answer_carries_foods_portion_and_citations(monkeypatch):
    model = Model(understand(), DRAFT)
    result, calls, model = ask(monkeypatch, model, '高血压老人一日三餐怎么搭配，爱吃咸菜',
                               profile=DietProfile(age=78, conditions=['hypertension']))
    assert result.status == 'answered'
    assert '咸菜' in [food.name for food in result.foods]
    assert 'hypertension_salt' in [finding.id for finding in result.findings]
    assert result.portion_reference is not None and '谷类' in result.answer
    assert '【1】' in result.answer and '不构成疾病治疗饮食处方' in result.answer
    assert [citation.index for citation in result.citations] == [1]
    assert result.answer_checks.status == 'passed'
    assert result.steps == ['understand', 'extract_foods', 'assess_nutrition', 'retrieve', 'generate',
                            'validate', 'verify_grounding']
    assert len(model.calls) == 2 and len(model.review_calls) == 1


def test_food_allergy_emergency_short_circuits(monkeypatch):
    model = Model(understand(intent='education', possible_emergency=True))
    result, calls, model = ask(monkeypatch, model, '吃虾后嘴唇肿，喘不上气')
    assert result.status == 'emergency' and result.urgency == 'L1'
    assert 'anaphylaxis_food' in result.triage_rule_ids
    assert '120' in result.answer and not calls
    assert 'retrieve' not in result.steps


def test_prescription_request_returns_boundary(monkeypatch):
    model = Model(understand(intent='meal_plan'))
    result, calls, model = ask(monkeypatch, model, '给我一份肾病治疗食谱')
    assert result.status == 'boundary' and result.reason == 'prescription_diet_not_allowed'
    assert not calls
    assert result.boundary and '治疗饮食处方' in result.boundary
    assert result.portion_reference is None


def test_extreme_diet_request_returns_boundary(monkeypatch):
    model = Model(understand(intent='condition_diet'))
    result, calls, model = ask(monkeypatch, model, '生酮饮食能治糖尿病吗')
    assert result.status == 'boundary' and result.reason == 'extreme_diet_not_allowed'
    assert '生酮' in result.answer and not calls


def test_clarification_skips_retrieval(monkeypatch):
    model = Model(understand(needs_clarification=True, query=None, clarification='请补充老人的慢病情况。'))
    result, calls, model = ask(monkeypatch, model, '给老人安排一下饮食')
    assert result.status == 'clarification' and result.reason == 'missing_conditions'
    assert not calls and '请补充老人的慢病情况' in result.answer


def test_no_hits_keeps_food_and_risk_blocks(monkeypatch):
    model = Model(understand())
    result, calls, model = ask(monkeypatch, model, '高血压老人早餐吃咸菜配粥', hits=[],
                               profile=DietProfile(conditions=['hypertension']))
    assert result.status == 'insufficient' and result.reason == 'no_hits'
    assert '咸菜' in result.answer and '120' in result.answer
    assert '不构成疾病治疗饮食处方' in result.answer


def test_model_portion_invention_is_blocked(monkeypatch):
    unsafe = {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
              'paragraphs': [{'text': '每天吃 200 克米饭和 50 克瘦肉。', 'sources': [1], 'kind': 'meal'}]}
    model = Model(understand(), unsafe, unsafe)
    result, calls, model = ask(monkeypatch, model, '高血压一日三餐')
    assert result.status == 'insufficient' and result.reason == 'unsafe_paragraph'
    assert result.citations == []
    assert '200 克' not in result.answer


def test_declared_allergy_blocks_suggestion(monkeypatch):
    unsafe = {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
              'paragraphs': [{'text': '晚餐可以吃虾和青菜，补充优质蛋白。', 'sources': [1], 'kind': 'meal'}]}
    model = Model(understand(), unsafe, unsafe)
    result, calls, model = ask(monkeypatch, model, '晚饭吃什么', profile=DietProfile(allergies=['虾']))
    assert result.status == 'insufficient'
    assert '虾和青菜' not in result.answer


def test_review_failure_never_releases_the_draft(monkeypatch):
    model = Model(understand(), DRAFT, review='fail')
    result, calls, model = ask(monkeypatch, model, '高血压一日三餐')
    assert result.status == 'insufficient' and result.reason == 'grounding_review_failed'
    assert '杂粮粥搭配鸡蛋' not in result.answer
    assert result.citations == []


def test_diet_metrics_are_request_scoped(monkeypatch):
    model = Model(understand(), DRAFT)
    result, calls, model = ask(monkeypatch, model, '高血压一日三餐')
    assert result.metrics.llm_calls == 3
    assert set(result.metrics.stage_ms) >= {'understand', 'extract_foods', 'assess_nutrition', 'retrieve',
                                            'generate', 'validate', 'verify_grounding'}
