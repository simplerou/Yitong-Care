from copy import deepcopy
from datetime import date,datetime,timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.models.auth import Account
from app.operations.models import Credential,Draft,Execution,Event,ClinicalProfile,Shift
from app.operations.validator import get_validator
from validation_service.graph import DEMO
from validation_service.rules import evaluate
from app.operations.contracts import CheckRequest
PATIENT={'allergens':[],'diseases':[],'medicines':[],'energy_min':'80','energy_max':'200','protein_min':'2','sodium_max':'500','source':'虚构自动化测试，非临床资料'}
class Validator:
    def __init__(self):self.facts=deepcopy(DEMO);self.calls=[]
    def check(self,payload):self.calls.append(payload);return evaluate(CheckRequest.model_validate(payload),self.facts)
    def evidence(self,drug):return {'drug_id':drug,**self.facts['drugs'][drug]['evidence']}
    def catalog(self):return {'demo':True,'version':self.facts['version'],'drugs':list(self.facts['drugs'].values()),'foods':list(self.facts['foods'].values())}
@pytest.fixture()
def ops(client):
    api,_,factory=client;admin=api.headers['Authorization'];validator=Validator()
    api.app.dependency_overrides[get_validator]=lambda:validator
    tokens={'admin':admin};ids={}
    for i,role in enumerate(['medical','kitchen','nursing','finance','user']):
        phone=f'1395555000{i}';account=api.post('/api/auth/register',json={'phone':phone,'name':role,'password':'Care12345'}).json();ids[role]=account['id']
        with factory() as db:
            db.get(Account,account['id']).role=role;db.get(Account,account['id']).status='active'
            if role in ('medical','nursing'):db.add(Credential(account_id=account['id'],qualification='已核实测试任职',valid_until=date.today()+timedelta(days=365)))
            db.commit()
        tokens[role]='Bearer '+api.post('/api/auth/login',json={'phone':phone,'password':'Care12345'}).json()['token']
    api.headers['Authorization']=admin
    row=api.post('/api/residents',json={'name':'虚构老人','source':'测试','assigned_account_ids':[ids['user']]}).json()
    api.headers['Authorization']=tokens['medical']
    response=api.put('/api/operations/profiles/'+row['id'],json={**PATIENT,'version':0,'resident_version':1})
    assert response.status_code==200,response.text
    return api,factory,tokens,ids,row,validator

def submit(api,task,payload):
    response=api.post('/api/operations/run',json={'task':task,'payload':payload,'use_model':False})
    if task=='medication' and response.status_code==201:
        row=response.json();assert api.post(f"/api/operations/drafts/{row['id']}/sign",json={'version':row['version'],'note':'测试医生已核对'}).status_code==200
    return response
def med(row,amount='1'):return {'resident_id':row['id'],'medicines':[{'drug_id':'DEMO-A','mg_per_dose':amount,'times_daily':1}],'rationale':'人工核对虚构说明书'}
def approve(api,row,note='已核对虚构测试依据'):return api.post(f"/api/operations/drafts/{row['id']}/decision",json={'version':row['version'],'action':'approve','note':note})

def test_medical_approval_execution_and_idempotency(ops):
    api,factory,tokens,ids,r,v=ops
    response=submit(api,'medication',med(r));assert response.status_code==201,response.text
    draft=response.json()
    assert [s['node'] for s in draft['trace']]==['gateway','supervisor','evidence','precheck','role_agent','critic','human_interrupt']
    assert len(api.get('/api/operations/executions').json()['items'])==0
    api.headers['Authorization']=tokens['admin'];assert approve(api,draft,'').status_code==422
    result=approve(api,draft);assert result.status_code==200,result.text
    assert approve(api,draft).status_code==200
    with factory() as db:assert db.scalar(select(func.count()).select_from(Execution))==1
    api.headers['Authorization']=tokens['user'];item=api.get('/api/operations/executions').json()['items'][0]
    assert api.post(f"/api/operations/executions/{item['id']}/complete",json={'note':'按批准单核对完成'}).status_code==200
    assert api.post(f"/api/operations/executions/{item['id']}/complete",json={'note':'重复确认'}).status_code==200

def test_gateway_schema_and_kitchen_redaction(ops):
    api,factory,tokens,ids,r,v=ops;api.headers['Authorization']=tokens['kitchen']
    assert submit(api,'medication',med(r)).status_code==404
    token=api.post('/api/operations/constraints').json();assert r['id'] not in str(token)
    payload={'constraint_token':token['constraint_token'],'foods':[{'food_id':'DEMO-RICE','grams':'100'}],'title':'演示一日配餐'}
    assert submit(api,'menu',{**payload,'resident_id':r['id']}).status_code==422
    response=submit(api,'menu',payload);assert response.status_code==201,response.text
    assert r['id'] not in str(response.json()) and 'medicines' not in str(response.json())
    assert api.get('/api/operations/catalog').json().get('drugs') is None
    assert api.get('/api/operations/profiles/'+r['id']).status_code==404

def test_fail_closed_expiry_versions_and_service_failure(ops):
    api,factory,tokens,ids,r,v=ops
    assert submit(api,'medication',med(r,'100')).status_code==409
    draft=submit(api,'medication',med(r)).json();v.facts['version']='v2'
    api.headers['Authorization']=tokens['admin'];assert approve(api,draft).status_code==409
    v.facts['version']=DEMO['version']
    with factory() as db:db.get(Draft,draft['id']).expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert approve(api,draft).status_code==409
    api.headers['Authorization']=tokens['medical']
    class Offline:
        def evidence(self,drug):raise HTTPException(503,'服务不可用')
    api.app.dependency_overrides[get_validator]=lambda:Offline()
    assert submit(api,'medication',med(r)).status_code==503
    with factory() as db:assert db.scalar(select(func.count()).select_from(Draft))==1

def test_revision_ledger_and_food_drug_conflict_redaction(ops):
    api,factory,tokens,ids,r,v=ops;draft=submit(api,'medication',med(r)).json()
    result=api.put(f"/api/operations/drafts/{draft['id']}",json={'version':1,'payload':med(r,'2'),'route':'training','tag':'dose','reason':'核对后调整虚构输入'})
    assert result.status_code==200,result.text
    assert result.json()['proposed']!=result.json()['current']
    assert api.post(f"/api/operations/drafts/{draft['id']}/sign",json={'version':2,'note':'修改后重新核实'}).status_code==200
    api.headers['Authorization']=tokens['admin'];assert approve(api,result.json()).status_code==200
    ledger=api.get('/api/operations/corrections').json()['items'];assert ledger[0]['route']=='training'
    assert api.post(f"/api/operations/corrections/{ledger[0]['id']}/close",json={'note':'完成复盘'}).status_code==200
    assert api.get('/api/operations/dashboard').json()['unchanged_adoption']==0
    api.headers['Authorization']=tokens['user']
    response=submit(api,'meal_swap',{'resident_id':r['id'],'foods':[{'food_id':'DEMO-GRAPE','grams':'200'}],'reason':'测试'})
    assert response.status_code==409
    assert 'DEMO-A' not in str(response.json())

def test_approval_rechecks_qualification_and_source(ops):
    api,factory,tokens,ids,r,v=ops;draft=submit(api,'medication',med(r)).json()
    with factory() as db:db.get(Credential,ids['medical']).valid_until=date.today()-timedelta(days=1);db.commit()
    api.headers['Authorization']=tokens['admin'];assert approve(api,draft).status_code==404
    with factory() as db:
        db.get(Credential,ids['medical']).valid_until=date.today()+timedelta(days=1);db.get(ClinicalProfile,r['id']).version+=1;db.commit()
    assert approve(api,draft).status_code==409

def test_schedule_and_finance_code_payroll(ops):
    api,factory,tokens,ids,r,v=ops
    start=(datetime.now()+timedelta(days=2)).replace(hour=8,minute=0,second=0,microsecond=0)
    shift={'account_id':ids['user'],'start_at':start.isoformat(),'end_at':(start+timedelta(hours=8)).isoformat(),'hourly_rate':'25.50'}
    api.headers['Authorization']=tokens['nursing'];response=submit(api,'schedule',{'shifts':[shift]});assert response.status_code==201,response.text
    api.headers['Authorization']=tokens['admin'];assert approve(api,response.json()).status_code==200
    with factory() as db:
        s=db.scalar(select(Shift));s.checked_in=s.start_at;s.checked_out=s.end_at;db.commit()
    api.headers['Authorization']=tokens['finance'];assert submit(api,'schedule',{'shifts':[shift]}).status_code==404
    payroll=api.get('/api/operations/payroll',params={'month':start.strftime('%Y-%m')}).json()
    assert payroll['lines'][0]['amount']=='204.00'
    response=submit(api,'payroll',{'month':start.strftime('%Y-%m')});assert response.status_code==201,response.text
    api.headers['Authorization']=tokens['admin'];assert approve(api,response.json()).status_code==200

def test_role_change_revokes_session_and_old_draft(ops):
    api,factory,tokens,ids,r,v=ops;draft=submit(api,'medication',med(r)).json()
    api.headers['Authorization']=tokens['admin']
    assert api.put('/api/operations/staff',json={'account_id':ids['medical'],'role':'kitchen'}).status_code==200
    api.headers['Authorization']=tokens['medical'];assert api.get('/api/operations/identity').status_code==401
    token=api.post('/api/auth/login',json={'phone':'13955550000','password':'Care12345'}).json()['token']
    api.headers['Authorization']='Bearer '+token
    assert api.get('/api/operations/drafts/'+draft['id']).status_code==404

def test_caregiver_report_goes_to_medical_inbox_without_a_model(ops):
    api,factory,tokens,ids,r,v=ops
    api.headers['Authorization']=tokens['user']
    response=submit(api,'incident',{'resident_id':r['id'],'severity':'urgent','observation':'发药后恶心，已联系值班医护'})
    assert response.status_code==201,response.text
    assert submit(api,'meal_swap',{'resident_id':r['id'],'foods':[{'food_id':'DEMO-RICE','grams':'100'}],'reason':'申请换餐'}).status_code==201
    api.headers['Authorization']=tokens['kitchen'];assert api.get('/api/operations/medical-inbox').status_code==404
    api.headers['Authorization']=tokens['medical']
    inbox=api.get('/api/operations/medical-inbox').json()['items'];assert len(inbox)==1
    assert inbox[0]['observation']=='发药后恶心，已联系值班医护'
    assert api.post(f"/api/operations/medical-inbox/{inbox[0]['id']}/ack",json={'note':'已安排现场复核'}).status_code==200
    with factory() as db:assert db.scalar(select(func.count()).select_from(Execution))==0


def test_model_repair_is_bounded_and_schema_cannot_change_the_order(ops):
    api,factory,tokens,ids,r,v=ops
    from app.services.chat.llm import get_llm
    class Model:
        calls=0
        def function_call(self,messages,tools):
            self.calls+=1
            return {'tool_calls':[{'id':str(self.calls),'function':{'name':'approve','arguments':'{}'}}]}
    model=Model();api.app.dependency_overrides[get_llm]=lambda:model
    response=api.post('/api/operations/run',json={'task':'medication','payload':med(r),'use_model':True})
    assert response.status_code==502 and model.calls==2
    with factory() as db:assert db.scalar(select(func.count()).select_from(Draft))==0

def test_legacy_selection_cannot_bypass_professional_conflict_gate(ops):
    api,factory,tokens,ids,r,v=ops
    from tests.api.test_meals import save,publish,WEEK
    api.headers['Authorization']=tokens['admin']
    menu=save(api);assert publish(api,menu,ack=True).status_code==200
    api.headers['Authorization']=tokens['user']
    url='/api/meals/residents/'+r['id']
    assert api.get(url,params={'week_start':WEEK}).json()['professional_workflow'] is True
    result=api.put(url,json={'menu_id':menu['id'],'day':0,'meal':'breakfast','option_id':menu['slots'][0]['options'][0]['id']})
    assert result.status_code==403
