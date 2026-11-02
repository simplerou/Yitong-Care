from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import BusinessError
from app.models.medication_conversation import MedicationTurn
from app.schemas.medication import MedicationAnswer, MedicationProfile
from app.services.medication import drugs

BASE = '/api/agents/medication'


def answer(**updates):
    base = dict(status='answered', urgency='L3', required_action='pharmacist_advice',
                answer='本次识别到的药物：华法林、阿司匹林\n\n相互作用与用药风险：\n· 【需尽快核对】抗凝药与抗血小板药同用\n\n不构成处方。',
                drugs=drugs.assess('华法林和阿司匹林', []).drugs,
                interactions=drugs.assess('华法林和阿司匹林', []).interactions,
                table_version=drugs.TABLE_VERSION, disclaimer='以上为用药科普信息，不构成处方。',
                model='test-qwen', knowledge_scope=['general'], steps=['understand', 'extract_medications'])
    base.update(updates)
    return MedicationAnswer(**base)


def test_config_exposes_scope_and_topics(client):
    api, *_ = client
    body = api.get(f'{BASE}/config').json()
    assert body['table_version'] == drugs.TABLE_VERSION
    assert body['workflow'] == 'langgraph' and body['streaming'] is False
    assert 'interaction' in body['topics'] and body['knowledge_scope']
    assert 'configured' in body and 'disclaimer' in body


def test_chat_validates_payload_and_runs_graph(client, monkeypatch):
    api, *_ = client
    from app.services.chat.llm import get_llm
    from app.services.web.tavily import get_web_search
    from app.schemas.retrieval import SearchHit

    class FakeLLM:
        model = 'fake-med'

        def __init__(self): self.calls = 0

        def ensure_configured(self): pass

        def complete_json(self, system, payload, max_tokens=1800):
            self.calls += 1
            if self.calls == 1:
                return {'supported': True, 'needs_clarification': False, 'clarification': None,
                        'query': '华法林与阿司匹林同用的出血风险', 'topic': 'interaction', 'drugs': ['华法林', '阿司匹林'],
                        'missing_fields': [], 'needs_freshness': False, 'possible_emergency': False, 'route': 'medication'}
            return {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
                    'paragraphs': [{'text': '华法林与阿司匹林同用会增加出血风险，需让医生或药师核对。', 'sources': [1], 'kind': 'caution'}]}

        def review_json(self, system, payload):
            evidence = {item['index']: item['text'] for item in payload['evidence']}
            return {'assessments': [{'paragraph': item['paragraph'], 'supported': True, 'addresses_question': True,
                                     'reason': 'supported',
                                     'quotes': [{'source_index': 1, 'text': evidence[1][:40], 'span_ids': []}]}
                                    for item in payload['paragraphs']]}

    api.app.dependency_overrides[get_llm] = lambda: FakeLLM()
    api.app.dependency_overrides[get_web_search] = lambda: SimpleNamespace(configured=False)
    text = '华法林与阿司匹林合用会增加出血风险，应由医生评估。'
    hit = SearchHit(chunk_id=1, doc_id='med', kb_id='general', doc_name='合理用药手册', type='TXT',
                    source='本地上传', seq=1, start=0, end=len(text), chars=len(text), text=text,
                    score=.9, cos=.9, lexical_score=1.0)
    monkeypatch.setattr('app.agents.medication_orchestrator.hybrid.search',
                        lambda *a, **kw: SimpleNamespace(hits=[hit], log_id='log', vector_count=1))
    response = api.post(f'{BASE}/chat', json={'question': '华法林和阿司匹林一起吃要紧吗',
                                             'medications': [{'name': '华法林'}, {'name': '阿司匹林', 'frequency': 'once_daily'}]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'answered' and body['urgency'] == 'L3'
    assert body['interactions'][0]['id'] == 'anticoagulant_antiplatelet'
    assert body['citations'][0]['hit']['chunk_id'] == 1
    assert body['disclaimer'] and body['table_version'] == drugs.TABLE_VERSION
    assert api.post(f'{BASE}/chat', json={'question': '  '}).status_code == 422
    assert api.post(f'{BASE}/chat', json={'question': 'x', 'profile': {'age': 80, 'name': '张三'}}).status_code == 422


def test_dose_request_is_boundary_without_llm_generation(client, monkeypatch):
    api, *_ = client
    from app.services.chat.llm import get_llm
    from app.services.web.tavily import get_web_search

    class FakeLLM:
        model = 'fake-med'

        def ensure_configured(self): pass

        def complete_json(self, system, payload, max_tokens=1800):
            return {'supported': True, 'needs_clarification': False, 'clarification': None,
                    'query': '氨氯地平剂量', 'topic': 'timing', 'drugs': ['氨氯地平'],
                    'missing_fields': [], 'needs_freshness': False, 'possible_emergency': False,
                    'route': 'medication'}

        def review_json(self, system, payload): pytest.fail('boundary must not generate')

    api.app.dependency_overrides[get_llm] = lambda: FakeLLM()
    api.app.dependency_overrides[get_web_search] = lambda: SimpleNamespace(configured=False)
    monkeypatch.setattr('app.agents.medication_orchestrator.hybrid.search',
                        lambda *a, **kw: pytest.fail('boundary must not retrieve'))
    response = api.post(f'{BASE}/chat', json={'question': '能把氨氯地平加到两片吗'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'boundary' and body['reason'] == 'dose_change_not_allowed'
    assert '两片' not in body['answer']
    assert body['boundary']


def conversation(api):
    response = api.post(f'{BASE}/conversations')
    assert response.status_code == 201, response.text
    return response.json()['id']


def send(api, key, question='华法林和阿司匹林一起吃要紧吗', request_id=None, retry=False, **extra):
    return api.post(f'{BASE}/conversations/{key}/turns',
                    json={'request_id': request_id or str(uuid4()), 'question': question, 'retry': retry, **extra})


def test_conversation_persists_snapshot_and_dedupes(client, monkeypatch):
    api, storage, factory = client
    calls = []

    def run(request, *args, **kwargs):
        calls.append(request)
        return answer(dialogue_state={'drugs': ['华法林', '阿司匹林'], 'topic': 'interaction', 'frequency': 'unknown',
                                      'symptoms': [], 'age': None, 'conditions': []})

    monkeypatch.setattr('app.api.v1.medication_chat.run_medication', run)
    key = conversation(api)
    request_id = str(uuid4())
    first = send(api, key, '华法林和阿司匹林一起吃要紧吗', request_id)
    assert first.status_code == 200, first.text
    turn = first.json()
    assert turn['status'] == 'succeeded'
    assert turn['response']['interactions'][0]['id'] == 'anticoagulant_antiplatelet'
    assert turn['response']['drugs'][0]['name'] == '华法林'
    again = send(api, key, '华法林和阿司匹林一起吃要紧吗', request_id)
    assert again.json() == turn and len(calls) == 1
    assert send(api, key, '其他问题', request_id).status_code == 409
    assert send(api, key, '带历史的问题', history=[]).status_code == 422
    detail = api.get(f'{BASE}/conversations/{key}').json()
    assert detail['turns'][0]['response'] == turn['response']
    assert detail['conversation']['title'] == '华法林和阿司匹林一起吃要紧吗'
    assert api.delete(f'{BASE}/conversations/{key}').status_code == 204
    from sqlalchemy import func, select
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(MedicationTurn)) == 0


def test_failed_turn_retry_and_history(client, monkeypatch):
    api, storage, factory = client
    captured = []

    def run(request, *args, **kwargs):
        captured.append(request)
        if len(captured) == 2: raise BusinessError('模型超时', 504)
        return answer(dialogue_state=request.dialogue_state)

    monkeypatch.setattr('app.api.v1.medication_chat.run_medication', run)
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
    monkeypatch.setattr('app.api.v1.medication_chat.run_medication', lambda *a, **kw: answer())
    key = conversation(api)
    ok = api.put(f'{BASE}/conversations/{key}/profile',
                 json={'profile': {'age': 82, 'conditions': ['ckd'], 'allergies': ['青霉素']}})
    assert ok.status_code == 200, ok.text
    assert ok.json()['profile']['age'] == 82
    assert api.put(f'{BASE}/conversations/{key}/profile', json={'profile': {'id_card': '3301'}}).status_code == 422


def test_progress_endpoint_reads_saved_stage(client, monkeypatch):
    api, *_ = client
    monkeypatch.setattr('app.api.v1.medication_chat.run_medication', lambda *a, **kw: answer())
    key = conversation(api)
    request_id = str(uuid4())
    send(api, key, '华法林和阿司匹林', request_id)
    progress = api.get(f'{BASE}/conversations/{key}/turns/{request_id}/progress').json()
    assert progress['status'] == 'succeeded' and progress['stage'] == 'completed'
    assert api.get(f'{BASE}/conversations/{key}/turns/{uuid4()}/progress').status_code == 404
