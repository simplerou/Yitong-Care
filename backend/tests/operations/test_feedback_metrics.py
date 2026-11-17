from sqlalchemy import select,func
from app.operations.models import Event
from app.services.chat.llm import get_llm
from tests.operations.test_workflow import ops,med,submit
from tests.operations.test_role_agents import NativeModel,medical_calls


def test_feedback_scope_evidence_and_idempotent_resolution(ops):
    api,factory,tokens,ids,resident,validator=ops
    draft=submit(api,'medication',med(resident)).json()
    changed=api.put(f"/api/operations/drafts/{draft['id']}",json={'version':1,'payload':med(resident,'2'),'route':'agent','tag':'dose','reason':'专业内部复盘详情'})
    assert changed.status_code==200
    path=f"/api/operations/drafts/{draft['id']}/feedback"
    entry=api.get(path).json()['items'][0]
    assert entry['before']!=entry['after'] and entry['can_resolve']
    assert entry['validation_snapshot']['previous_version']==1 and entry['validation_snapshot']['version']==2
    assert entry['validation_snapshot']['before']['graph_hash']
    api.headers['Authorization']=tokens['admin']
    redacted=api.get(path).json()['items'][0]
    assert redacted['before']=={} and redacted['after']=={} and '专业内部复盘详情' not in str(redacted)
    close=f"/api/operations/feedback/{entry['id']}/resolve"
    assert api.post(close,json={'note':'试图代替专业人员闭环'}).status_code==404
    api.headers['Authorization']=tokens['kitchen'];assert api.get(path).status_code==404
    api.headers['Authorization']=tokens['medical']
    assert api.post(close,json={'note':' '}).status_code==422
    assert api.post(close,json={'note':'复测通过，已记录改进项'}).json()['items'][0]['closed']
    assert api.post(close,json={'note':'重复提交'}).status_code==200
    assert api.get(path).json()['items'][0]['resolution_note']=='复测通过，已记录改进项'
    with factory() as db:assert db.scalar(select(func.count()).select_from(Event).where(Event.action=='feedback_resolved'))==1
    api.headers['Authorization']=tokens['admin']
    assert api.get('/api/operations/dashboard').json()['periods']['week']['feedback']['agent']=={'total':1,'open':0,'closed':1}


def test_revision_refreshes_risk_and_confirmation_requirement(ops):
    api,factory,tokens,ids,resident,validator=ops;original=validator.check
    validator.check=lambda request:{**original(request),'risk':1}
    draft=submit(api,'medication',med(resident)).json();assert draft['risk']==1
    validator.check=lambda request:{**original(request),'risk':3}
    changed=api.put(f"/api/operations/drafts/{draft['id']}",json={'version':1,'payload':med(resident,'2'),'route':'rule','tag':'dose','reason':'重新核对风险'}).json()
    assert changed['risk']==3 and changed['professional_signoff'] is None
    api.headers['Authorization']=tokens['admin']
    assert api.post(f"/api/operations/drafts/{draft['id']}/decision",json={'version':2,'action':'reject','note':''}).status_code==422


def test_native_metrics_count_valid_calls_and_rejections_separately(ops):
    api,factory,tokens,ids,resident,validator=ops
    model=NativeModel(medical_calls());api.app.dependency_overrides[get_llm]=lambda:model
    assert api.post('/api/operations/assistant/medical',json={'resident_id':resident['id'],'text':'准备虚构草稿'}).status_code==201
    api.headers['Authorization']=tokens['kitchen']
    bad=NativeModel([('food_catalog',{'resident_id':resident['id']}),('read_record',{})]);api.app.dependency_overrides[get_llm]=lambda:bad
    assert api.post('/api/operations/assistant/kitchen',json={'text':'参数注入测试'}).status_code==502
    api.headers['Authorization']=tokens['admin'];summary=api.get('/api/operations/dashboard').json()['react_tools']
    assert summary['successes']==5 and summary['failures']==0 and summary['rejected']==2
    assert summary['denominator']==5 and summary['success_rate']==1
    with factory() as db:
        entries=list(db.scalars(select(Event).where(Event.action.like('react_tool_%'))))
        assert len(entries)==7 and resident['id'] not in str([e.data for e in entries])


def test_native_external_tool_failure_is_audited_even_when_request_aborts(ops):
    from app.core.exceptions import BusinessError
    api,factory,tokens,ids,resident,validator=ops
    def offline(drug):raise BusinessError('外部服务不可用',503)
    validator.evidence=offline
    model=NativeModel([('read_record',{}),('drug_evidence',{'drug_id':'DEMO-A'})]);api.app.dependency_overrides[get_llm]=lambda:model
    assert api.post('/api/operations/assistant/medical',json={'resident_id':resident['id'],'text':'查证'}).status_code==503
    api.headers['Authorization']=tokens['admin']
    summary=api.get('/api/operations/dashboard').json()['react_tools']
    assert summary['successes']==1 and summary['failures']==1 and summary['success_rate']==.5


import pytest
@pytest.mark.parametrize('client',[False],indirect=True)
def test_feedback_is_available_in_strict_six_role_product(client):
    from tests.api.test_six_role_product import provision
    from tests.operations.test_workflow import Validator,PATIENT
    from app.operations.validator import get_validator
    api,_,factory=client;tokens,ids=provision(api)
    api.app.dependency_overrides[get_validator]=lambda:Validator()
    api.headers['Authorization']=tokens['nursing']
    resident=api.post('/api/residents',json={'name':'虚构复盘对象','source':'测试','assigned_account_ids':[ids['user']]}).json()
    api.headers['Authorization']=tokens['medical']
    assert api.put('/api/operations/profiles/'+resident['id'],json={**PATIENT,'version':0,'resident_version':1}).status_code==200
    draft=submit(api,'medication',med(resident)).json()
    assert api.put(f"/api/operations/drafts/{draft['id']}",json={'version':1,'payload':med(resident,'2'),'route':'rule','tag':'dose','reason':'专业复盘'}).status_code==200
    path=f"/api/operations/drafts/{draft['id']}/feedback"
    item=api.get(path).json()['items'][0]
    assert api.post(f"/api/operations/feedback/{item['id']}/resolve",json={'note':'核实并复测'}).status_code==200
    api.headers['Authorization']=tokens['admin']
    assert api.get(path).json()['items'][0]['before']=={}
    assert api.get('/api/operations/corrections').status_code==404
