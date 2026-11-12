import pytest
from sqlalchemy import select,func
from app.models.resident import Resident
from app.operations.validator import get_validator
from tests.operations.test_workflow import Validator,PATIENT

pytestmark=pytest.mark.parametrize('client',[False],indirect=True)

def provision(api):
    admin=api.headers['Authorization'];tokens={'admin':admin};ids={}
    for n,role in enumerate(['medical','kitchen','nursing','finance','user']):
        phone=f'1398888000{n}'
        account=api.post('/api/auth/register',json={'phone':phone,'name':role,'password':'Role12345','requested_role':role}).json();ids[role]=account['id']
        response=api.post(f"/api/account-reviews/{account['id']}/decision",json={'version':1,'action':'approve','role':role,'qualification':'线下核实' if role in ('medical','nursing') else '','valid_until':'2099-01-01' if role in ('medical','nursing') else None})
        assert response.status_code==200,response.text
        tokens[role]='Bearer '+api.post('/api/auth/login',json={'phone':phone,'password':'Role12345'}).json()['token']
    return tokens,ids

def test_normal_application_has_no_old_agents_or_maintenance_pages(client):
    api,_,_=client
    for path in ['/api/agents/policy/config','/api/agents/health/config','/api/agents/medication/config','/api/agents/diet/config','/api/agents/safety/config','/api/agents/mind/config','/api/documents','/api/retrieval/logs','/api/operations/audit']:
        assert api.get(path).status_code==404,path
    paths=api.get('/openapi.json').json()['paths']
    assert not any(p.startswith('/api/agents/') for p in paths)

def test_nursing_owns_archives_and_assignments_not_director(client):
    api,_,factory=client;tokens,ids=provision(api)
    assert api.get('/api/auth/caregivers').status_code==403
    assert api.post('/api/residents',json={'name':'不应创建','source':'测试'}).status_code==403
    api.headers['Authorization']=tokens['nursing']
    rows=api.get('/api/auth/caregivers').json();assert len(rows)==1 and rows[0]['id']==ids['user']
    record=api.post('/api/residents',json={'name':'护理部建档','source':'虚构入院登记'}).json();assert 'id' in record
    response=api.put(f"/api/residents/{record['id']}/assignments",json={'version':1,'account_ids':[ids['user']],'reason':'护理分工'})
    assert response.status_code==200,response.text
    api.headers['Authorization']=tokens['admin']
    assert api.get('/api/residents').status_code==403
    assert api.get('/api/residents/'+record['id']).status_code==403
    assert api.put(f"/api/residents/{record['id']}/assignments",json={'version':2,'account_ids':[],'reason':'越权'}).status_code==403
    api.headers['Authorization']=tokens['user'];assert api.get('/api/residents/'+record['id']).status_code==200
    assert api.put('/api/residents/'+record['id'],json={'name':'试图修改','source':'测试','version':2,'change_reason':'越权'}).status_code==403
    api.headers['Authorization']=tokens['finance'];assert api.get('/api/residents').status_code==403
    with factory() as db:assert db.scalar(select(func.count()).select_from(Resident))==1

def test_caregiver_swap_is_validated_then_kitchen_confirms(client):
    api,_,factory=client;tokens,ids=provision(api)
    validator=Validator();api.app.dependency_overrides[get_validator]=lambda:validator
    api.headers['Authorization']=tokens['nursing']
    record=api.post('/api/residents',json={'name':'虚构选餐老人','source':'测试','assigned_account_ids':[ids['user']]}).json()
    api.headers['Authorization']=tokens['medical']
    assert api.put('/api/operations/profiles/'+record['id'],json={**PATIENT,'version':0,'resident_version':1}).status_code==200
    api.headers['Authorization']=tokens['user']
    card=api.get('/api/operations/identity').json();assert set(card['tasks'])=={'incident','meal_swap'}
    response=api.post('/api/operations/run',json={'task':'meal_swap','payload':{'resident_id':record['id'],'foods':[{'food_id':'DEMO-RICE','grams':'100'}],'reason':'申请调整一日方案'},'use_model':False})
    assert response.status_code==201,response.text
    request=response.json();api.headers['Authorization']=tokens['kitchen']
    assert record['id'] not in str(api.get('/api/operations/drafts/'+request['id']).json())
    assert api.post(f"/api/operations/drafts/{request['id']}/decision",json={'version':1,'action':'approve','note':'已核对备餐方案'}).status_code==200
    prep=api.get('/api/operations/executions').json()['items'][0]
    assert api.post(f"/api/operations/executions/{prep['id']}/complete",json={'note':'已备餐'}).status_code==200
    api.headers['Authorization']=tokens['user'];item=api.get('/api/operations/executions').json()['items'][0]
    assert api.post(f"/api/operations/executions/{item['id']}/complete",json={'note':'已核对发放'}).status_code==200

def test_care_review_belongs_to_nursing_and_medical_ack_is_separate(client):
    api,_,_=client;tokens,ids=provision(api)
    api.headers['Authorization']=tokens['nursing']
    record=api.post('/api/residents',json={'name':'虚构照护对象','source':'测试','assigned_account_ids':[ids['user']]}).json()
    api.headers['Authorization']=tokens['user']
    response=api.post('/api/operations/run',json={'task':'incident','payload':{'resident_id':record['id'],'severity':'routine','observation':'午餐后轻微不适，已通知现场医护'},'use_model':True})
    assert response.status_code==201,response.text
    draft=response.json()
    api.headers['Authorization']=tokens['admin']
    assert not api.get('/api/operations/drafts/'+draft['id']).json()['can_approve']
    api.headers['Authorization']=tokens['medical']
    inbox=api.get('/api/operations/medical-inbox').json()['items']
    assert len(inbox)==1
    assert api.post(f"/api/operations/medical-inbox/{inbox[0]['id']}/ack",json={'note':'医护已核实'}).status_code==200
    api.headers['Authorization']=tokens['nursing']
    detail=api.get('/api/operations/drafts/'+draft['id']).json()
    assert detail['status']=='pending' and detail['can_approve']
    assert api.post(f"/api/operations/drafts/{draft['id']}/decision",json={'version':1,'action':'approve','note':'照护跟进已核实'}).status_code==200


def test_expired_nursing_cannot_manage_assignments(client):
    from datetime import date
    from app.operations.models import Credential
    api,_,factory=client;tokens,ids=provision(api)
    with factory() as db:
        db.get(Credential,ids['nursing']).valid_until=date(2000,1,1);db.commit()
    api.headers['Authorization']=tokens['nursing']
    for path in ['/api/auth/caregivers','/api/residents','/api/residents/assignees']:
        assert api.get(path).status_code==403,path
    assert api.get('/api/operations/staff').status_code==404
