from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import BusinessError
from app.models.safety_conversation import SafetyTurn
from app.schemas.safety import SafetyAnswer, SafetyProfile
from app.services.safety import hazards

BASE = '/api/agents/safety'


def answer(**updates):
    base = dict(status='answered', urgency='L4', required_action='self_care',
                answer='本次提到的居家隐患：\n· 卫生间：马桶旁或淋浴区没有扶手\n\n建议安装扶手并铺防滑垫。\n\n'
                       '以上为居家安全与跌倒预防建议，不构成医疗诊断。',
                hazards=[], risk_factors=[], risk_level='low', post_fall=[], post_fall_advice=None,
                table_version=hazards.TABLE_VERSION, disclaimer='以上为居家安全与跌倒预防建议，不构成医疗诊断。',
                model='test-qwen', knowledge_scope=['general'], steps=['understand', 'extract_hazards'])
    base.update(updates)
    return SafetyAnswer(**base)


def test_config_exposes_scope_and_intents(client):
    api, *_ = client
    body = api.get(f'{BASE}/config').json()
    assert body['table_version'] == hazards.TABLE_VERSION
    assert body['workflow'] == 'langgraph' and body['streaming'] is False
    assert 'fall_event' in body['intents'] and body['knowledge_scope']
    assert 'disclaimer' in body


def test_chat_runs_real_graph_with_hazards_and_citations(client, monkeypatch):
    api, *_ = client
    from app.services.chat.llm import get_llm
    from app.services.web.tavily import get_web_search
    from app.schemas.retrieval import SearchHit

    class FakeLLM:
        model = 'fake-safety'

        def __init__(self): self.calls = 0

        def ensure_configured(self): pass

        def complete_json(self, system, payload, max_tokens=1800):
            self.calls += 1
            if self.calls == 1:
                return {'supported': True, 'needs_clarification': False, 'clarification': None,
                        'query': '老年人居家防跌倒 卫生间扶手', 'intent': 'environment', 'missing_fields': [],
                        'needs_freshness': False, 'possible_emergency': False, 'route': 'safety'}
            return {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
                    'paragraphs': [{'text': '马桶旁和淋浴区安装扶手，地面铺防滑垫，起夜路上加感应夜灯。',
                                    'sources': [1], 'kind': 'environment'}]}

        def review_json(self, system, payload):
            evidence = {item['index']: item['text'] for item in payload['evidence']}
            return {'assessments': [{'paragraph': item['paragraph'], 'supported': True, 'addresses_question': True,
                                     'reason': 'supported',
                                     'quotes': [{'source_index': 1, 'text': evidence[1][:40], 'span_ids': []}]}
                                    for item in payload['paragraphs']]}

    api.app.dependency_overrides[get_llm] = lambda: FakeLLM()
    api.app.dependency_overrides[get_web_search] = lambda: SimpleNamespace(configured=False)
    text = '卫生间马桶旁与淋浴区安装扶手，扶手常见高度 70–80 cm，地面保持干燥并铺防滑垫。'
    hit = SearchHit(chunk_id=1, doc_id='safety', kb_id='general', doc_name='老年人跌倒干预技术指南', type='TXT',
                    source='本地上传', seq=1, start=0, end=len(text), chars=len(text), text=text,
                    score=.9, cos=.9, lexical_score=1.0)
    monkeypatch.setattr('app.agents.safety_orchestrator.hybrid.search',
                        lambda *a, **kw: SimpleNamespace(hits=[hit], log_id='log', vector_count=1))
    response = api.post(f'{BASE}/chat', json={'question': '卫生间装扶手大概多高'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'answered'
    assert body['hazards'][0]['id'] == 'bath_grab_bar'
    assert body['citations'][0]['hit']['chunk_id'] == 1
    assert '70–80 cm' in body['answer'] or '70' in body['answer']
    assert api.post(f'{BASE}/chat', json={'question': '  '}).status_code == 422
    assert api.post(f'{BASE}/chat', json={'question': 'x', 'profile': {'name': '张三'}}).status_code == 422


def test_fall_emergency_short_circuits_api(client, monkeypatch):
    api, *_ = client
    from app.services.chat.llm import get_llm
    from app.services.web.tavily import get_web_search

    class FakeLLM:
        model = 'fake-safety'

        def ensure_configured(self): pass

        def complete_json(self, system, payload, max_tokens=1800):
            return {'supported': True, 'needs_clarification': False, 'clarification': None,
                    'query': '跌倒后髋部疼痛', 'intent': 'fall_event', 'missing_fields': [],
                    'needs_freshness': False, 'possible_emergency': True, 'route': 'safety'}

        def review_json(self, system, payload): pytest.fail('emergency must not generate')

    api.app.dependency_overrides[get_llm] = lambda: FakeLLM()
    api.app.dependency_overrides[get_web_search] = lambda: SimpleNamespace(configured=False)
    monkeypatch.setattr('app.agents.safety_orchestrator.hybrid.search',
                        lambda *a, **kw: pytest.fail('emergency must not retrieve'))
    response = api.post(f'{BASE}/chat', json={'question': '我爸摔倒了，髋部疼得站不起来'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'emergency' and body['urgency'] == 'L1'
    assert '120' in body['answer'] and 'retrieve' not in body['steps']


def conversation(api):
    response = api.post(f'{BASE}/conversations')
    assert response.status_code == 201, response.text
    return response.json()['id']


def send(api, key, question='卫生间装扶手大概多高', request_id=None, retry=False, **extra):
    return api.post(f'{BASE}/conversations/{key}/turns',
                    json={'request_id': request_id or str(uuid4()), 'question': question, 'retry': retry, **extra})


def test_conversation_persists_snapshot_and_dedupes(client, monkeypatch):
    api, storage, factory = client
    calls = []

    def run(request, *args, **kwargs):
        calls.append(request)
        return answer(dialogue_state={'conditions': [], 'medications': [], 'previous_falls': 1,
                                      'living_alone': True, 'mobility': 'independent',
                                      'rooms': ['卫生间'], 'topic': 'environment'})

    monkeypatch.setattr('app.api.v1.safety_chat.run_safety', run)
    key = conversation(api)
    request_id = str(uuid4())
    first = send(api, key, '卫生间装扶手大概多高', request_id)
    assert first.status_code == 200, first.text
    turn = first.json()
    assert turn['status'] == 'succeeded'
    assert turn['response']['table_version'] == hazards.TABLE_VERSION
    again = send(api, key, '卫生间装扶手大概多高', request_id)
    assert again.json() == turn and len(calls) == 1
    assert send(api, key, '其他问题', request_id).status_code == 409
    assert send(api, key, '带历史的问题', history=[]).status_code == 422
    detail = api.get(f'{BASE}/conversations/{key}').json()
    assert detail['turns'][0]['response'] == turn['response']
    assert detail['conversation']['title'] == '卫生间装扶手大概多高'
    assert api.delete(f'{BASE}/conversations/{key}').status_code == 204
    from sqlalchemy import func, select
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SafetyTurn)) == 0


def test_failed_turn_retry_and_history(client, monkeypatch):
    api, storage, factory = client
    captured = []

    def run(request, *args, **kwargs):
        captured.append(request)
        if len(captured) == 2: raise BusinessError('模型超时', 504)
        return answer(dialogue_state=request.dialogue_state)

    monkeypatch.setattr('app.api.v1.safety_chat.run_safety', run)
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
    monkeypatch.setattr('app.api.v1.safety_chat.run_safety', lambda *a, **kw: answer())
    key = conversation(api)
    ok = api.put(f'{BASE}/conversations/{key}/profile',
                 json={'profile': {'age': 82, 'living_alone': True, 'previous_falls': 2, 'mobility': 'cane'}})
    assert ok.status_code == 200, ok.text
    assert ok.json()['profile']['previous_falls'] == 2
    assert api.put(f'{BASE}/conversations/{key}/profile', json={'profile': {'id_card': '3301'}}).status_code == 422


def test_progress_endpoint_reads_saved_stage(client, monkeypatch):
    api, *_ = client
    monkeypatch.setattr('app.api.v1.safety_chat.run_safety', lambda *a, **kw: answer())
    key = conversation(api)
    request_id = str(uuid4())
    send(api, key, '卫生间扶手多高', request_id)
    progress = api.get(f'{BASE}/conversations/{key}/turns/{request_id}/progress').json()
    assert progress['status'] == 'succeeded' and progress['stage'] == 'completed'
    assert api.get(f'{BASE}/conversations/{key}/turns/{uuid4()}/progress').status_code == 404
