from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import BusinessError
from app.models.mind_conversation import MindTurn
from app.schemas.mind import MindAnswer, MindProfile
from app.services.mind import emotions

BASE = '/api/agents/mind'


def answer(**updates):
    base = dict(status='answered', urgency='L3', required_action='self_care',
                answer='听到你这么说，我很心疼。\n\n可以先把难受的事写下来。\n\n'
                       '以上是陪伴与心理教育信息，不构成诊断。',
                signals=[], screening=None, risk_level='low', safety_plan=[], crisis_notice=None,
                table_version=emotions.TABLE_VERSION, disclaimer='不构成诊断',
                model='test-qwen', knowledge_scope=['general'], steps=['understand', 'assess_mind'])
    base.update(updates)
    return MindAnswer(**base)


def test_config_exposes_scope_and_intents(client):
    api, *_ = client
    body = api.get(f'{BASE}/config').json()
    assert body['table_version'] == emotions.TABLE_VERSION
    assert body['workflow'] == 'langgraph' and body['streaming'] is False
    assert 'emotional_support' in body['intents'] and body['knowledge_scope']
    assert 'disclaimer' in body


def test_chat_runs_real_graph_with_empathy_and_citations(client, monkeypatch):
    api, *_ = client
    from app.services.chat.llm import get_llm
    from app.services.web.tavily import get_web_search
    from app.schemas.retrieval import SearchHit

    class FakeLLM:
        model = 'fake-mind'

        def __init__(self): self.calls = 0

        def ensure_configured(self): pass

        def complete_json(self, system, payload, max_tokens=1800):
            self.calls += 1
            if self.calls == 1:
                return {'supported': True, 'needs_clarification': False, 'clarification': None,
                        'query': '丧亲哀伤 陪伴 老年人 心理', 'intent': 'grief', 'missing_fields': [],
                        'needs_freshness': False, 'possible_crisis': False, 'route': 'mind'}
            return {'sufficient': True, 'coverage': 'complete', 'missing_topics': [], 'paragraphs': [
                {'text': '听到你说老伴走了以后一直高兴不起来，这种空落落的感觉一定很难熬。', 'sources': [], 'kind': 'empathy'},
                {'text': '哀伤没有固定时间表，可以留一个固定时段想念，其他时间把注意力放回当下的小事。',
                 'sources': [1], 'kind': 'advice'}]}

        def review_json(self, system, payload):
            evidence = {item['index']: item['text'] for item in payload['evidence']}
            assessments = []
            for item in payload['paragraphs']:
                if item.get('kind') == 'empathy':
                    assessments.append({'paragraph': item['paragraph'], 'supported': True,
                                        'addresses_question': True, 'reason': 'supported', 'quotes': []})
                else:
                    assessments.append({'paragraph': item['paragraph'], 'supported': True,
                                        'addresses_question': True, 'reason': 'supported',
                                        'quotes': [{'source_index': 1, 'text': evidence[1][:40], 'span_ids': []}]})
            return {'assessments': assessments}

    api.app.dependency_overrides[get_llm] = lambda: FakeLLM()
    api.app.dependency_overrides[get_web_search] = lambda: SimpleNamespace(configured=False)
    text = '哀伤是失去亲人后的正常反应，可以留固定时段思念，其他时间把注意力放回当下。'
    hit = SearchHit(chunk_id=1, doc_id='mind', kb_id='general', doc_name='老年心理关怀指南', type='TXT',
                    source='本地上传', seq=1, start=0, end=len(text), chars=len(text), text=text,
                    score=.9, cos=.9, lexical_score=1.0)
    monkeypatch.setattr('app.agents.mind_orchestrator.hybrid.search',
                        lambda *a, **kw: SimpleNamespace(hits=[hit], log_id='log', vector_count=1))
    response = api.post(f'{BASE}/chat', json={'question': '老伴走了以后，一直高兴不起来'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'answered' and body['urgency'] == 'L3'
    assert body['advice'][0]['kind'] == 'empathy'
    assert body['citations'][0]['hit']['chunk_id'] == 1
    assert '不构成诊断' in body['answer']
    assert api.post(f'{BASE}/chat', json={'question': '  '}).status_code == 422
    assert api.post(f'{BASE}/chat', json={'question': 'x', 'profile': {'name': '张三'}}).status_code == 422


def test_crisis_short_circuits_api(client, monkeypatch):
    api, *_ = client
    from app.services.chat.llm import get_llm
    from app.services.web.tavily import get_web_search

    class FakeLLM:
        model = 'fake-mind'

        def ensure_configured(self): pass

        def complete_json(self, system, payload, max_tokens=1800):
            return {'supported': True, 'needs_clarification': False, 'clarification': None,
                    'query': '自杀意念 危机干预', 'intent': 'emotional_support', 'missing_fields': [],
                    'needs_freshness': False, 'possible_crisis': True, 'route': 'mind'}

        def review_json(self, system, payload): pytest.fail('crisis must not generate')

    api.app.dependency_overrides[get_llm] = lambda: FakeLLM()
    api.app.dependency_overrides[get_web_search] = lambda: SimpleNamespace(configured=False)
    monkeypatch.setattr('app.agents.mind_orchestrator.hybrid.search',
                        lambda *a, **kw: pytest.fail('crisis must not retrieve'))
    response = api.post(f'{BASE}/chat', json={'question': '我不想活了'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'crisis' and body['urgency'] == 'L1'
    assert '12356' in body['answer'] and '120' in body['answer']
    assert body['crisis_notice']


def conversation(api):
    response = api.post(f'{BASE}/conversations')
    assert response.status_code == 201, response.text
    return response.json()['id']


def send(api, key, question='老伴走了以后，一直高兴不起来', request_id=None, retry=False, **extra):
    return api.post(f'{BASE}/conversations/{key}/turns',
                    json={'request_id': request_id or str(uuid4()), 'question': question, 'retry': retry, **extra})


def test_conversation_persists_snapshot_and_dedupes(client, monkeypatch):
    api, storage, factory = client
    calls = []

    def run(request, *args, **kwargs):
        calls.append(request)
        return answer(dialogue_state={'topic': 'grief', 'mood_words': ['难过'], 'duration': '一直',
                                      'sleep': '', 'support_person': '', 'losses': ['老伴走了']})

    monkeypatch.setattr('app.api.v1.mind_chat.run_mind', run)
    key = conversation(api)
    request_id = str(uuid4())
    first = send(api, key, '老伴走了以后，一直高兴不起来', request_id)
    assert first.status_code == 200, first.text
    turn = first.json()
    assert turn['status'] == 'succeeded'
    assert turn['response']['table_version'] == emotions.TABLE_VERSION
    again = send(api, key, '老伴走了以后，一直高兴不起来', request_id)
    assert again.json() == turn and len(calls) == 1
    assert send(api, key, '其他问题', request_id).status_code == 409
    assert send(api, key, '带历史的问题', history=[]).status_code == 422
    detail = api.get(f'{BASE}/conversations/{key}').json()
    assert detail['turns'][0]['response'] == turn['response']
    assert detail['conversation']['title'] == '老伴走了以后，一直高兴不起来'
    assert api.delete(f'{BASE}/conversations/{key}').status_code == 204
    from sqlalchemy import func, select
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(MindTurn)) == 0


def test_failed_turn_retry_and_history(client, monkeypatch):
    api, storage, factory = client
    captured = []

    def run(request, *args, **kwargs):
        captured.append(request)
        if len(captured) == 2: raise BusinessError('模型超时', 504)
        return answer(dialogue_state=request.dialogue_state)

    monkeypatch.setattr('app.api.v1.mind_chat.run_mind', run)
    key = conversation(api)
    assert send(api, key, '第一问').status_code == 200
    failed_id = str(uuid4())
    assert send(api, key, '第二问', failed_id).status_code == 504
    row = api.get(f'{BASE}/conversations/{key}').json()['turns'][-1]
    assert row['status'] == 'failed' and row['error'] == '模型超时'
    assert send(api, key, '第二问', failed_id, retry=True).status_code == 200
    history = captured[-1].history
    assert [turn.role for turn in history] == ['user', 'assistant']


def test_profile_update_rejects_identity_fields(client, monkeypatch):
    api, *_ = client
    monkeypatch.setattr('app.api.v1.mind_chat.run_mind', lambda *a, **kw: answer())
    key = conversation(api)
    ok = api.put(f'{BASE}/conversations/{key}/profile',
                 json={'profile': {'age': 78, 'living_alone': True, 'recent_loss': True, 'has_confidant': False}})
    assert ok.status_code == 200, ok.text
    assert ok.json()['profile']['recent_loss'] is True
    assert api.put(f'{BASE}/conversations/{key}/profile', json={'profile': {'id_card': '3301'}}).status_code == 422


def test_progress_endpoint_reads_saved_stage(client, monkeypatch):
    api, *_ = client
    monkeypatch.setattr('app.api.v1.mind_chat.run_mind', lambda *a, **kw: answer())
    key = conversation(api)
    request_id = str(uuid4())
    send(api, key, '最近睡不好', request_id)
    progress = api.get(f'{BASE}/conversations/{key}/turns/{request_id}/progress').json()
    assert progress['status'] == 'succeeded' and progress['stage'] == 'completed'
    assert api.get(f'{BASE}/conversations/{key}/turns/{uuid4()}/progress').status_code == 404
