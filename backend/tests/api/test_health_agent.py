from uuid import uuid4

import pytest

from app.core.exceptions import BusinessError
from app.models.health_conversation import HealthConversation, HealthTurn
from app.schemas.health import HealthAnswer, Triage, VitalsAssessment
from app.services.health import vitals
from test_health_graph import hit

BASE = '/api/agents/health'


def answer(**updates):
    base = dict(status='answered', urgency='L3', required_action='clinic_visit',
                answer='本次记录：150/95 mmHg → 1级高血压。\n\n建议复测并记录。【1】\n\n' + '以上为健康科普信息。',
                vitals_assessment=vitals.assess('早上 150/95', [], [], __import__('app.schemas.health', fromlist=['HealthProfile']).HealthProfile()),
                citations=[], retrieved_hits=[hit()], web_status='not_used', table_version=vitals.TABLE_VERSION,
                disclaimer='以上为健康科普信息', model='test-qwen', knowledge_scope=['general'],
                steps=['understand', 'assess_vitals', 'triage', 'retrieve', 'generate', 'validate', 'verify_grounding'])
    base.update(updates)
    from app.schemas.chat import Citation
    if 'citations' not in updates: base['citations'] = [Citation(index=1, hit=hit())]
    return HealthAnswer(**base)


def test_config_exposes_scope_and_table_version(client):
    api, *_ = client
    body = api.get(f'{BASE}/config').json()
    assert body['table_version'] == vitals.TABLE_VERSION
    assert body['workflow'] == 'langgraph' and body['streaming'] is False
    assert 'blood_pressure' in body['metrics']
    assert body['knowledge_scope'] and 'disclaimer' in body
    assert 'api_key' not in body and 'llm_api_key' not in body


def test_chat_validates_payload(client, monkeypatch):
    api, *_ = client
    monkeypatch.setattr('app.api.v1.health_chat.run_health', lambda *a, **kw: answer())
    ok = api.post(f'{BASE}/chat', json={'question': '早上 150/95', 'vitals': [
        {'metric': 'blood_pressure', 'systolic': 150, 'diastolic': 95, 'unit': 'mmHg', 'context': 'home'}]})
    assert ok.status_code == 200, ok.text
    assert ok.json()['status'] == 'answered'
    assert api.post(f'{BASE}/chat', json={'question': '   '}).status_code == 422
    assert api.post(f'{BASE}/chat', json={'question': 'x', 'vitals': [
        {'metric': 'blood_pressure', 'systolic': 90, 'unit': 'mmHg'}]}).status_code == 422
    assert api.post(f'{BASE}/chat', json={'question': 'x', 'profile': {'age': 90, 'name': '张三'}}).status_code == 422


def conversation(api):
    response = api.post(f'{BASE}/conversations')
    assert response.status_code == 201, response.text
    return response.json()['id']


def send(api, key, question='早上 150/95 高吗', request_id=None, retry=False, **extra):
    return api.post(f'{BASE}/conversations/{key}/turns',
                    json={'request_id': request_id or str(uuid4()), 'question': question, 'retry': retry, **extra})


def test_conversation_persists_snapshot_and_dedupes(client, monkeypatch):
    api, storage, factory = client
    calls = []

    def run(request, *args, **kwargs):
        calls.append(request)
        return answer(dialogue_state={'metric': 'blood_pressure', 'value_text': '150/95', 'symptoms': [],
                                      'age': None, 'conditions': [], 'topic': '', 'last_reading_keys': []})

    monkeypatch.setattr('app.api.v1.health_chat.run_health', run)
    key = conversation(api)
    request_id = str(uuid4())
    first = send(api, key, '早上 150/95 高吗', request_id)
    assert first.status_code == 200, first.text
    turn = first.json()
    assert turn['status'] == 'succeeded'
    assert turn['response']['vitals_assessment']['readings'][0]['category_code'] == 'stage1'
    assert turn['response']['table_version'] == vitals.TABLE_VERSION
    assert '判读' in turn['response']['answer'] or '本次记录' in turn['response']['answer']
    again = send(api, key, '早上 150/95 高吗', request_id)
    assert again.json() == turn and len(calls) == 1
    assert send(api, key, '其他问题', request_id).status_code == 409
    assert send(api, key, '带历史的问题', history=[]).status_code == 422

    detail = api.get(f'{BASE}/conversations/{key}').json()
    assert detail['turns'][0]['response'] == turn['response']
    assert detail['conversation']['title'] == '早上 150/95 高吗'
    assert api.get(f'{BASE}/conversations').json()['items'][0]['id'] == key
    assert api.delete(f'{BASE}/conversations/{key}').status_code == 204
    assert api.get(f'{BASE}/conversations/{key}').status_code == 404
    from sqlalchemy import func, select
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(HealthTurn)) == 0


def test_server_side_history_and_failed_retry(client, monkeypatch):
    api, storage, factory = client
    captured = []

    def run(request, *args, **kwargs):
        captured.append(request)
        if len(captured) == 2: raise BusinessError('模型超时', 504)
        return answer(dialogue_state=request.dialogue_state)

    monkeypatch.setattr('app.api.v1.health_chat.run_health', run)
    key = conversation(api)
    assert send(api, key, '第一问').status_code == 200
    failed_id = str(uuid4())
    failed = send(api, key, '第二问', failed_id)
    assert failed.status_code == 504
    row = api.get(f'{BASE}/conversations/{key}').json()['turns'][-1]
    assert row['status'] == 'failed' and row['error'] == '模型超时'
    assert send(api, key, '第二问', failed_id, retry=True).status_code == 200
    assert len(captured) == 3
    history = captured[-1].history
    assert [turn.role for turn in history] == ['user', 'assistant']
    assert history[0].content == '第一问'


def test_profile_update_is_bounded_and_rejects_foreign_fields(client, monkeypatch):
    api, *_ = client
    monkeypatch.setattr('app.api.v1.health_chat.run_health', lambda *a, **kw: answer())
    key = conversation(api)
    ok = api.put(f'{BASE}/conversations/{key}/profile',
                 json={'profile': {'age': 82, 'conditions': ['hypertension'], 'medications': ['氨氯地平']}})
    assert ok.status_code == 200, ok.text
    assert ok.json()['profile']['age'] == 82
    bad = api.put(f'{BASE}/conversations/{key}/profile', json={'profile': {'id_card': '3301'}})
    assert bad.status_code == 422


def test_progress_endpoint_reads_saved_stage(client, monkeypatch):
    api, *_ = client
    monkeypatch.setattr('app.api.v1.health_chat.run_health', lambda *a, **kw: answer())
    key = conversation(api)
    request_id = str(uuid4())
    send(api, key, '早上 150/95', request_id)
    progress = api.get(f'{BASE}/conversations/{key}/turns/{request_id}/progress').json()
    assert progress['status'] == 'succeeded' and progress['stage'] == 'completed'
    assert api.get(f'{BASE}/conversations/{key}/turns/{uuid4()}/progress').status_code == 404


class FakeLLM:
    model = 'fake-agent'

    def __init__(self):
        self.calls = 0

    def ensure_configured(self): pass

    def complete_json(self, system, payload, max_tokens=1800):
        self.calls += 1
        if self.calls == 1:
            return {'supported': True, 'needs_clarification': False, 'clarification': None,
                    'query': '家庭自测血压 145/92 判读', 'metric': 'blood_pressure', 'missing_fields': [],
                    'needs_freshness': False, 'possible_emergency': False, 'route': 'health',
                    'reported_value': '145/92'}
        return {'sufficient': True, 'coverage': 'complete', 'missing_topics': [],
                'paragraphs': [{'text': '家庭自测血压 145/92 mmHg 高于 135/85 mmHg 的判读切点，属偏高范围，建议复测并记录。',
                                'sources': [1], 'kind': 'explain'}]}

    def review_json(self, system, payload):
        evidence = {item['index']: item['text'] for item in payload['evidence']}
        return {'assessments': [{'paragraph': item['paragraph'], 'supported': True, 'addresses_question': True,
                                 'reason': 'supported',
                                 'quotes': [{'source_index': 1, 'text': evidence[1][:40], 'span_ids': []}]}
                                for item in payload['paragraphs']]}


def test_chat_runs_the_real_graph_with_deterministic_triage(client, monkeypatch):
    """The endpoint must run the graph, not a stubbed answer: DI and serialisation are part of the contract."""
    from app.services.chat.llm import get_llm
    from app.services.web.tavily import get_web_search
    from app.schemas.retrieval import SearchHit
    from types import SimpleNamespace

    api, *_ = client
    api.app.dependency_overrides[get_llm] = lambda: FakeLLM()
    api.app.dependency_overrides[get_web_search] = lambda: SimpleNamespace(configured=False)
    text = '家庭自测血压：≥135/85 mmHg 视为偏高，家庭自测标准低于诊室测量。应复测并记录。'
    hit = SearchHit(chunk_id=1, doc_id='h1', kb_id='general', doc_name='家庭血压监测指南', type='TXT',
                    source='本地上传', seq=1, start=0, end=len(text), chars=len(text), text=text,
                    score=.9, cos=.9, lexical_score=1.0)
    monkeypatch.setattr('app.agents.health_orchestrator.hybrid.search',
                        lambda *a, **kw: SimpleNamespace(hits=[hit], log_id='log-1', vector_count=1))
    response = api.post(f'{BASE}/chat', json={'question': '家里量的血压 145/92，要紧吗'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'answered' and body['urgency'] == 'L3'
    assert body['vitals_assessment']['readings'][0]['category_code'] == 'stage1'
    assert body['citations'][0]['hit']['chunk_id'] == 1
    assert '【1】' in body['answer'] and '不构成诊断或处方' in body['answer']
    assert body['table_version'] == vitals.TABLE_VERSION


def test_chat_emergency_path_returns_without_retrieval(client, monkeypatch):
    from app.services.chat.llm import get_llm
    from app.services.web.tavily import get_web_search

    api, *_ = client
    model = FakeLLM()
    api.app.dependency_overrides[get_llm] = lambda: model
    api.app.dependency_overrides[get_web_search] = lambda: __import__('types').SimpleNamespace(configured=False)
    monkeypatch.setattr('app.agents.health_orchestrator.hybrid.search',
                        lambda *a, **kw: pytest.fail('emergency must not retrieve'))
    response = api.post(f'{BASE}/chat', json={'question': '我爸胸口压得慌，出冷汗十几分钟了'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'emergency' and body['urgency'] == 'L1'
    assert '120' in body['answer'] and 'retrieve' not in body['steps']
    assert model.calls == 1
