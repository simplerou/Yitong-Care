import json
import stat
from types import SimpleNamespace
from scripts import inspect_policy_failure as script


def test_export_writes_real_file_without_model_or_database_calls(monkeypatch,tmp_path,capsys):
    row=SimpleNamespace(id='test-request',conversation_id='test-session',seq=1,created_at='2026-10-30',question='是不是9999元？',response={'reason':'unsupported_numeric_expansion','answer_checks':{'issues':['generation_amount_not_in_evidence:paragraph_1']}})
    class Database:
        def __init__(self): self.reads=0
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def scalars(self,*args):
            self.reads+=1
            return SimpleNamespace(all=lambda:[row] if self.reads==1 else [])
    monkeypatch.setattr(script,'SessionLocal',Database)
    monkeypatch.setattr(script,'BACKEND_DIR',tmp_path)
    assert script.main([])==0
    path=next((tmp_path/'var'/'diagnostics').glob('*.json'))
    assert json.loads(path.read_text())['response']==row.response
    assert stat.S_IMODE(path.stat().st_mode)==0o600
    assert '诊断文件：' in capsys.readouterr().out


def test_latest_conversation_exports_all_turn_statuses_in_order(monkeypatch,tmp_path):
 rows=[SimpleNamespace(id=f'request-{i}',seq=i,created_at='2026-10-30',question=f'用户第{i}问',status='succeeded' if i!=2 else 'failed',response={'answer':f'助手第{i}答','reason':'missing_conditions'}) for i in range(1,5)]
 class Database:
  def __enter__(self): return self
  def __exit__(self,*args): pass
  def scalar(self,*args): return SimpleNamespace(id='session',title='最近会话')
  def scalars(self,*args): return SimpleNamespace(all=lambda:list(reversed(rows)))
 monkeypatch.setattr(script,'SessionLocal',Database)
 monkeypatch.setattr(script,'BACKEND_DIR',tmp_path)
 assert script.main(['--latest-conversation'])==0
 data=json.loads(next((tmp_path/'var'/'diagnostics').glob('*.json')).read_text())
 assert data['mode']=='latest_conversation_read_only'
 assert [turn['seq'] for turn in data['turns']]==[1,2,3,4]
 assert data['turns'][1]['status']=='failed' and not data['earlier_turns_omitted']


def test_latest_turn_exports_no_results_and_full_web_diagnostics(monkeypatch,tmp_path):
 row=SimpleNamespace(id='request',conversation_id='session',seq=7,created_at='2026-10-30',question='服务项目',response={'reason':'model_insufficient','web_status':'no_results','web_sources':[],'web_diagnostics':{'search_query':'温州市龙湾区 长期护理保险 护理服务目录 服务项目','search_count':7,'extraction_returned':7,'rejected_counts':{'service_catalog_missing':7},'pages':[{'title':'报告','url':'https://wenzhou.gov.cn/report','outcome':'rejected','reason':'service_catalog_missing'}]}})
 class DB:
  def __init__(self): self.reads=0
  def __enter__(self): return self
  def __exit__(self,*args): pass
  def scalars(self,*args):
   self.reads+=1;return SimpleNamespace(all=lambda:[row] if self.reads==1 else [])
 monkeypatch.setattr(script,'SessionLocal',DB);monkeypatch.setattr(script,'BACKEND_DIR',tmp_path)
 assert script.main(['--latest-turn'])==0
 data=json.loads(next((tmp_path/'var'/'diagnostics').glob('*.json')).read_text())
 assert data['question']=='服务项目' and data['response']['web_diagnostics']==row.response['web_diagnostics']
 assert data['mode']=='latest_saved_turn_no_model_calls'
