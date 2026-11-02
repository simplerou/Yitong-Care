from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import BusinessError
from app.models.diet_conversation import DietTurn
from app.schemas.diet import DietAnswer, DietProfile
from app.services.diet import foods

BASE = '/api/agents/diet'


def answer(**updates):
    base = dict(status='answered', urgency='L3', required_action='dietitian_referral',
                answer='本次提到的食物：\n· 咸菜（高盐）\n\n建议减少腌制品，用葱姜蒜和醋调味，具体份量见参考表。\n\n'
                       '以上为膳食营养建议，不构成疾病治疗饮食处方。',
                foods=foods.extract('咸菜', [])[0], findings=[], unknown_foods=[],
                portion_reference=foods.portion_reference(), nutrition_risks=['盐摄入偏高'],
                table_version=foods.TABLE_VERSION, disclaimer='以上为膳食营养建议，不构成疾病治疗饮食处方。',
                model='test-qwen', knowledge_scope=['general'], steps=['understand', 'extract_foods'])
    base.update(updates)
    return DietAnswer(**base)


def test_config_exposes_scope_and_intents(client):
    api, *_ = client
    body = api.get(f'{BASE}/config').json()
    assert body['table_version'] == foods.TABLE_VERSION
    assert body['workflow'] == 'langgraph' and body['streaming'] is False
    assert 'meal_plan' in body['intents'] and body['knowledge_scope']
    assert 'disclaimer' in body


def test_chat_runs_real_graph_and_blocks_portions(client, monkeypatch):
    api, *_ = client
    from app.services.chat.llm import get_llm
    from app.services.web.tavily import get_web_search
    from app.schemas.retrieval import SearchHit

    class FakeLLM:
        model = 'fake-diet'

        def __init__(self): self.calls = 0

        def ensure_configured(self): pass

        def complete_json(self, system, payload, max_tokens=1800):
            self.calls += 1
            if self.calls == 1:
                return {'supported': True, 'needs_clarification': False, 'clarification': None,
                        'query': '老年人高血压一日三餐 控盐', 'intent': 'meal_plan', 'foods': ['咸菜'],
                        'missing_fields': [], 'needs_freshness': False, 'possible_emergency': False, 'route': 'diet'}
            return {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
                    'paragraphs': [{'text': '主食粗细搭配，多吃蔬菜和优质蛋白，少用腌制品和酱油。',
                                    'sources': [1], 'kind': 'meal'}]}

        def review_json(self, system, payload):
            evidence = {item['index']: item['text'] for item in payload['evidence']}
            return {'assessments': [{'paragraph': item['paragraph'], 'supported': True, 'addresses_question': True,
                                     'reason': 'supported',
                                     'quotes': [{'source_index': 1, 'text': evidence[1][:40], 'span_ids': []}]}
                                    for item in payload['paragraphs']]}

    api.app.dependency_overrides[get_llm] = lambda: FakeLLM()
    api.app.dependency_overrides[get_web_search] = lambda: SimpleNamespace(configured=False)
    text = '老年人膳食应食物多样，主食粗细搭配，控制食盐用量，多吃新鲜蔬菜水果。'
    hit = SearchHit(chunk_id=1, doc_id='diet', kb_id='general', doc_name='中国老年人膳食指南', type='TXT',
                    source='本地上传', seq=1, start=0, end=len(text), chars=len(text), text=text,
                    score=.9, cos=.9, lexical_score=1.0)
    monkeypatch.setattr('app.agents.diet_orchestrator.hybrid.search',
                        lambda *a, **kw: SimpleNamespace(hits=[hit], log_id='log', vector_count=1))
    response = api.post(f'{BASE}/chat', json={'question': '高血压老人一日三餐怎么搭配，爱吃咸菜',
                                             'profile': {'age': 78, 'conditions': ['hypertension']}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'answered'
    assert body['foods'][0]['name'] == '咸菜'
    assert body['portion_reference']['table_version'] == foods.TABLE_VERSION
    assert body['citations'][0]['hit']['chunk_id'] == 1
    assert '200 克' not in body['answer']
    assert api.post(f'{BASE}/chat', json={'question': '  '}).status_code == 422
    assert api.post(f'{BASE}/chat', json={'question': 'x', 'profile': {'name': '张三'}}).status_code == 422


def test_allergy_emergency_short_circuits(client, monkeypatch):
    api, *_ = client
    from app.services.chat.llm import get_llm
    from app.services.web.tavily import get_web_search

    class FakeLLM:
        model = 'fake-diet'

        def ensure_configured(self): pass

        def complete_json(self, system, payload, max_tokens=1800):
            return {'supported': True, 'needs_clarification': False, 'clarification': None,
                    'query': '进食后过敏反应', 'intent': 'education', 'foods': ['虾'],
                    'missing_fields': [], 'needs_freshness': False, 'possible_emergency': True, 'route': 'diet'}

        def review_json(self, system, payload): pytest.fail('emergency must not generate')

    api.app.dependency_overrides[get_llm] = lambda: FakeLLM()
    api.app.dependency_overrides[get_web_search] = lambda: SimpleNamespace(configured=False)
    monkeypatch.setattr('app.agents.diet_orchestrator.hybrid.search',
                        lambda *a, **kw: pytest.fail('emergency must not retrieve'))
    response = api.post(f'{BASE}/chat', json={'question': '吃虾后嘴唇肿，喘不上气'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'emergency' and body['urgency'] == 'L1'
    assert '120' in body['answer'] and 'retrieve' not in body['steps']


def conversation(api):
    response = api.post(f'{BASE}/conversations')
    assert response.status_code == 201, response.text
    return response.json()['id']


def send(api, key, question='高血压老人一日三餐怎么搭配', request_id=None, retry=False, **extra):
    return api.post(f'{BASE}/conversations/{key}/turns',
                    json={'request_id': request_id or str(uuid4()), 'question': question, 'retry': retry, **extra})


def test_conversation_persists_snapshot_and_dedupes(client, monkeypatch):
    api, storage, factory = client
    calls = []

    def run(request, *args, **kwargs):
        calls.append(request)
        return answer(dialogue_state={'conditions': ['hypertension'], 'allergies': [], 'chewing': 'normal',
                                      'swallowing': 'normal', 'dislikes': [], 'foods_suggested': ['咸菜'],
                                      'topic': 'meal_plan'})

    monkeypatch.setattr('app.api.v1.diet_chat.run_diet', run)
    key = conversation(api)
    request_id = str(uuid4())
    first = send(api, key, '高血压老人一日三餐怎么搭配', request_id)
    assert first.status_code == 200, first.text
    turn = first.json()
    assert turn['status'] == 'succeeded'
    assert turn['response']['foods'][0]['name'] == '咸菜'
    assert turn['response']['portion_reference']['table_version'] == foods.TABLE_VERSION
    again = send(api, key, '高血压老人一日三餐怎么搭配', request_id)
    assert again.json() == turn and len(calls) == 1
    assert send(api, key, '其他问题', request_id).status_code == 409
    assert send(api, key, '带历史的问题', history=[]).status_code == 422
    detail = api.get(f'{BASE}/conversations/{key}').json()
    assert detail['turns'][0]['response'] == turn['response']
    assert detail['conversation']['title'] == '高血压老人一日三餐怎么搭配'
    assert api.delete(f'{BASE}/conversations/{key}').status_code == 204
    from sqlalchemy import func, select
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(DietTurn)) == 0


def test_failed_turn_retry_and_history(client, monkeypatch):
    api, storage, factory = client
    captured = []

    def run(request, *args, **kwargs):
        captured.append(request)
        if len(captured) == 2: raise BusinessError('模型超时', 504)
        return answer(dialogue_state=request.dialogue_state)

    monkeypatch.setattr('app.api.v1.diet_chat.run_diet', run)
    key = conversation(api)
    assert send(api, key, '第一问').status_code == 200
    failed_id = str(uuid4())
    assert send(api, key, '第二问', failed_id).status_code == 504
    row = api.get(f'{BASE}/conversations/{key}').json()['turns'][-1]
    assert row['status'] == 'failed' and row['error'] == '模型超时'
    assert send(api, key, '第二问', failed_id, retry=True).status_code == 200
    history = captured[-1].history
    assert [turn.role for turn in history] == ['user', 'assistant']
    assert history[0].content == '第一问'


def test_profile_update_rejects_identity_fields(client, monkeypatch):
    api, *_ = client
    monkeypatch.setattr('app.api.v1.diet_chat.run_diet', lambda *a, **kw: answer())
    key = conversation(api)
    ok = api.put(f'{BASE}/conversations/{key}/profile',
                 json={'profile': {'age': 82, 'conditions': ['hypertension'], 'chewing': 'difficult'}})
    assert ok.status_code == 200, ok.text
    assert ok.json()['profile']['chewing'] == 'difficult'
    assert api.put(f'{BASE}/conversations/{key}/profile', json={'profile': {'id_card': '3301'}}).status_code == 422


def test_progress_endpoint_reads_saved_stage(client, monkeypatch):
    api, *_ = client
    monkeypatch.setattr('app.api.v1.diet_chat.run_diet', lambda *a, **kw: answer())
    key = conversation(api)
    request_id = str(uuid4())
    send(api, key, '高血压一日三餐', request_id)
    progress = api.get(f'{BASE}/conversations/{key}/turns/{request_id}/progress').json()
    assert progress['status'] == 'succeeded' and progress['stage'] == 'completed'
    assert api.get(f'{BASE}/conversations/{key}/turns/{uuid4()}/progress').status_code == 404
