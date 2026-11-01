"""Request-local measurements. Never retain prompts, evidence or provider payloads."""
from contextvars import ContextVar
from functools import wraps
from time import perf_counter


active_metrics = ContextVar('policy_execution_metrics', default=None)


def record_usage(usage):
    metrics = active_metrics.get()
    if metrics is None or not isinstance(usage, dict): return
    prompt, completion = usage.get('prompt_tokens'), usage.get('completion_tokens')
    if type(prompt) is int and type(completion) is int and prompt >= 0 and completion >= 0:
        metrics.usage_calls += 1
        metrics.prompt_tokens += prompt
        metrics.completion_tokens += completion


class PolicyMetrics:
    def __init__(self):
        self.started = perf_counter()
        self.stage_ms = {}
        self.usage_calls = self.prompt_tokens = self.completion_tokens = 0
        self.llm_calls = 0
        self.llm_failures = 0
        self.llm_ms = 0.0

    def measure_node(self, name, node):
        @wraps(node)
        def measured(state):
            started = perf_counter()
            try:
                return node(state)
            finally:
                self.stage_ms[name] = self.stage_ms.get(name, 0.0) + (perf_counter() - started) * 1000
        return measured

    def snapshot(self):
        return dict(total_ms=round((perf_counter() - self.started) * 1000, 2),
                    stage_ms={name: round(value, 2) for name, value in self.stage_ms.items()},
                    llm_calls=self.llm_calls, llm_failures=self.llm_failures,
                    llm_ms=round(self.llm_ms, 2), usage_calls=self.usage_calls,
                    prompt_tokens=self.prompt_tokens if self.usage_calls else None,
                    completion_tokens=self.completion_tokens if self.usage_calls else None)


class MeasuredLLM:
    """Wrap logical model requests, including repair/review, without mutating a shared client."""
    def __init__(self, client, metrics):
        self.client = client
        self.metrics = metrics

    def __getattr__(self, name):
        return getattr(self.client, name)

    def _call(self, method, *args, **kwargs):
        self.metrics.llm_calls += 1
        started = perf_counter()
        token = active_metrics.set(self.metrics)
        try:
            return method(*args, **kwargs)
        except Exception:
            self.metrics.llm_failures += 1
            raise
        finally:
            active_metrics.reset(token)
            self.metrics.llm_ms += (perf_counter() - started) * 1000

    def complete_json(self, *args, **kwargs):
        return self._call(self.client.complete_json, *args, **kwargs)

    def review_json(self, *args, **kwargs):
        return self._call(self.client.review_json, *args, **kwargs)
