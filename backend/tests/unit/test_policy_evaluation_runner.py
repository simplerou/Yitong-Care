from types import SimpleNamespace
import json
from sqlalchemy.exc import SQLAlchemyError
from scripts import evaluate_policy as runner
from app.schemas.chat import PolicyAnswer


def test_validate_only_never_connects(monkeypatch):
    monkeypatch.setattr(runner,'SessionLocal',lambda:(_ for _ in ()).throw(AssertionError('must not connect')))
    assert runner.main(['--validate-only'])==0


def test_database_preflight_creates_blocked_report_without_models(monkeypatch,tmp_path):
    def fail(): raise SQLAlchemyError('sensitive connection details')
    monkeypatch.setattr(runner,'SessionLocal',fail)
    monkeypatch.setattr(runner,'get_llm',lambda:SimpleNamespace(ensure_configured=lambda:None))
    monkeypatch.setattr(runner,'get_embedder',lambda:SimpleNamespace(ensure_configured=lambda:None))
    monkeypatch.setattr(runner,'get_index_manager',lambda:None)
    monkeypatch.setattr(runner,'run_policy',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('must not run')))
    assert runner.main(['--case','P02','--output',str(tmp_path)])==1
    path=next(tmp_path.glob('*/report.json'));report=json.loads(path.read_text())
    assert report['status']=='blocked' and report['summary']['not_run']==1
    assert 'sensitive' not in path.read_text()


def test_web_cases_require_explicit_web_option():
    assert runner.main(['--case','W01','--validate-only'])==2


def test_multiturn_runner_uses_actual_previous_response(monkeypatch,tmp_path):
    from pathlib import Path
    from app.core.config import Settings
    from app.schemas.chat import Citation, AnswerChecks
    from test_policy_graph import hit
    reference=(runner.DATASET_PATH.parent/'reference.txt').read_text()
    doc=SimpleNamespace(id='d',name='baseline.pdf',kb_id='general',status='vectorized',updated_at='2026-10-29',content=reference)
    class DB:
        count=0
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,*args): return None
        def scalar(self,*args): return 1
        def scalars(self,*args):
            self.count+=1
            return SimpleNamespace(all=lambda:[doc] if self.count==1 else [])
    monkeypatch.setattr(runner,'SessionLocal',DB)
    monkeypatch.setattr(runner,'get_settings',lambda:Settings(_env_file=None,llm_model='test-model',embedding_model='test-embed'))
    monkeypatch.setattr(runner,'get_llm',lambda:SimpleNamespace(ensure_configured=lambda:None))
    monkeypatch.setattr(runner,'get_embedder',lambda:SimpleNamespace(ensure_configured=lambda:None))
    monkeypatch.setattr(runner,'get_index_manager',lambda:None)
    calls=[]
    def policy(request,*args,**kwargs):
        calls.append(request)
        text='真实第一轮回答：80至89周岁每月40元。' if len(calls)==1 else '90周岁每月100元。'
        source=hit().model_copy(update={'text':text})
        return PolicyAnswer(status='answered',answer=text+'【1】',citations=[Citation(index=1,hit=source)],retrieved_hits=[source],
            model='test-model',knowledge_scope=['general'],steps=['retrieve','verify_grounding'],answer_checks=AnswerChecks(status='passed'))
    monkeypatch.setattr(runner,'run_policy',policy)
    assert runner.main(['--case','P15','--output',str(tmp_path)])==0
    assert calls[1].history[1].content.startswith('真实第一轮回答')
    assert calls[1].question=='那90岁呢？'
    report=json.loads(next(tmp_path.glob('*/report.json')).read_text())
    assert report['summary']['automated_pass']==1
    assert report['results'][0]['manual_status']=='pending'
