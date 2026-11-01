import pytest
from app.services.chat.metrics import PolicyMetrics, MeasuredLLM


def test_counts_retries_and_failures_without_double_counting_review(monkeypatch):
    from app.services.chat import metrics as module
    clock = iter([0, 1, 2, 3, 4, 5, 6, 7])
    monkeypatch.setattr(module, 'perf_counter', lambda: next(clock))
    metrics = PolicyMetrics()
    class Client:
        model = 'fake'
        def complete_json(self, *args):
            if args[0] == 'fail': raise ValueError('private upstream body')
            return {'ok': True}
        def review_json(self, *args): return self.complete_json(*args)
    client = Client()
    measured = MeasuredLLM(client, metrics)
    measured.complete_json('ok')
    with pytest.raises(ValueError): measured.complete_json('fail')
    measured.review_json('ok')
    assert metrics.snapshot() == dict(total_ms=7000, stage_ms={}, llm_calls=3, llm_failures=1, llm_ms=3000,usage_calls=0,prompt_tokens=None,completion_tokens=None)
    assert measured.model == 'fake'
    assert not hasattr(client, 'metrics')


def test_stage_accumulates_repeated_execution_and_records_failure(monkeypatch):
    from app.services.chat import metrics as module
    clock = iter([0, 1, 2, 3, 5, 6])
    monkeypatch.setattr(module, 'perf_counter', lambda: next(clock))
    metrics = PolicyMetrics()
    def node(state):
        if state: raise RuntimeError('secret')
        return {'answer': 'ok'}
    wrapped = metrics.measure_node('generate', node)
    assert wrapped({}) == {'answer': 'ok'}
    with pytest.raises(RuntimeError): wrapped({'fail': True})
    snapshot = metrics.snapshot()
    assert snapshot['stage_ms'] == {'generate': 3000}
    assert 'secret' not in str(snapshot)


def test_old_answer_snapshots_need_no_metrics():
    from app.schemas.chat import PolicyAnswer
    answer = PolicyAnswer(status='clarification', answer='请提供地区', model='fake', knowledge_scope=[], steps=[])
    assert answer.metrics is None
