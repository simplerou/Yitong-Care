import json
from copy import deepcopy
from datetime import date
from sqlalchemy import select,func
from app.operations.models import Draft,Execution
from app.services.chat.llm import get_llm
from tests.operations.test_workflow import ops,med,approve

class NativeModel:
    def __init__(self,calls):self.calls=list(calls);self.messages=[];self.registries=[]
    def function_call(self,messages,tools):
        self.messages.append(deepcopy(messages));self.registries.append(deepcopy(tools))
        if not self.calls:return {'content':'已完成查证与校验，草稿等待人工确认。'}
        name,args=self.calls.pop(0)
        return {'tool_calls':[{'id':'call-'+str(len(self.messages)),'function':{'name':name,'arguments':json.dumps(args)}}]}

def medical_calls():
    args={'medicines':[{'drug_id':'DEMO-A','amount':'0.001','unit':'g','times_daily':1}],'rationale':'按医生指定剂量准备，仅虚构测试'}
    return [('read_record',{}),('drug_evidence',{'drug_id':'DEMO-A'}),('validate_medication',args),('medication_draft',args),('review_draft',{})]

def test_medical_native_react_converts_units_and_requires_signature(ops):
    api,factory,tokens,ids,r,validator=ops
    validator.facts['drugs']['DEMO-A']['cost_per_mg_cny']='2.50'
    model=NativeModel(medical_calls());api.app.dependency_overrides[get_llm]=lambda:model
    response=api.post('/api/operations/assistant/medical',json={'resident_id':r['id'],'text':'给所选老人加0.001g虚构药品A，仅准备草稿'})
    assert response.status_code==201,response.text
    draft=response.json();assert draft['current']['medicines'][0]['mg_per_dose']=='1.000'
    assert [t['tool'] for t in draft['trace'] if t['node']=='react_tool']==[x[0] for x in medical_calls()]
    assert draft['professional_signoff'] is None
    api.headers['Authorization']=tokens['admin']
    director=api.get('/api/operations/drafts/'+draft['id']).json()
    assert director['current']=={} and director['proposed']=={} and director['resident_name'] is None
    assert 'DEMO-A' not in str(director) and r['id'] not in str(director)
    assert director['validation']['cost']['amount_cny']=='2.50'
    assert approve(api,draft).status_code==409
    api.headers['Authorization']=tokens['medical']
    assert api.post(f"/api/operations/drafts/{draft['id']}/sign",json={'version':1,'note':'医生已核实单位、过敏与专业依据'}).status_code==200
    api.headers['Authorization']=tokens['admin'];assert approve(api,draft).status_code==200
    with factory() as db:assert db.scalar(select(func.count()).select_from(Execution))==1

def test_kitchen_react_has_no_record_or_drug_tools_or_observations(ops):
    api,factory,tokens,ids,r,validator=ops;api.headers['Authorization']=tokens['kitchen']
    from app.operations.models import ClinicalProfile
    with factory() as db:
        profile=db.get(ClinicalProfile,r['id']);profile.data={**profile.data,'medicines':[{'drug_id':'DEMO-A','mg_per_dose':'1','times_daily':1}]};profile.version+=1;db.commit()
    args={'foods':[{'food_id':'DEMO-RICE','grams':'100'}],'title':'虚构配餐','service_date':date.today().isoformat()}
    model=NativeModel([('constraints',{}),('food_catalog',{}),('nutrition_check',args),('menu_draft',args),('review_draft',{})])
    api.app.dependency_overrides[get_llm]=lambda:model
    response=api.post('/api/operations/assistant/kitchen',json={'text':'根据核实目录准备一日完整方案，仅演示'})
    assert response.status_code==201,response.text
    for registry in model.registries:
        names={x['function']['name'] for x in registry}
        assert 'read_record' not in names and 'drug_evidence' not in names and 'approve_swap' not in names
    text=str(model.messages)
    assert r['id'] not in text and '虚构老人' not in text and 'DEMO-A' not in text
    assert api.post('/api/operations/assistant/kitchen',json={'text':'排餐','resident_id':r['id']}).status_code==422

def test_tool_argument_injection_cannot_access_another_domain(ops):
    api,factory,tokens,ids,r,validator=ops;api.headers['Authorization']=tokens['kitchen']
    model=NativeModel([('food_catalog',{'resident_id':r['id']}),('read_record',{})]);api.app.dependency_overrides[get_llm]=lambda:model
    response=api.post('/api/operations/assistant/kitchen',json={'text':'尝试参数注入'})
    assert response.status_code==502
    with factory() as db:assert db.scalar(select(func.count()).select_from(Draft))==0

def test_signature_is_invalidated_by_revision(ops):
    api,factory,tokens,ids,r,validator=ops
    draft=api.post('/api/operations/run',json={'task':'medication','payload':med(r),'use_model':False}).json()
    assert api.post(f"/api/operations/drafts/{draft['id']}/sign",json={'version':1,'note':'已核对'}).status_code==200
    revised=api.put(f"/api/operations/drafts/{draft['id']}",json={'version':1,'payload':med(r,'2'),'route':'agent','tag':'dose','reason':'调整虚构输入'}).json()
    assert revised['professional_signoff'] is None
    api.headers['Authorization']=tokens['admin'];assert approve(api,revised).status_code==409

def test_supervisor_and_caregiver_tools_follow_identity_only(ops):
    api,factory,tokens,ids,r,validator=ops
    api.headers['Authorization']=tokens['user']
    card=api.get('/api/operations/identity').json()
    assert set(card['tools'])=={'execution_list','record','report_incident','validate_swap','swap_draft'} and set(card['tasks'])=={'incident','meal_swap'}
    api.headers['Authorization']=tokens['admin']
    assert set(api.get('/api/operations/identity').json()['tools'])=={'view_validation','view_cost','approve'}

def test_status_question_answers_without_creating_medication(ops):
    api,factory,tokens,ids,r,validator=ops
    class QueryModel(NativeModel):
        def function_call(self,messages,tools):
            if not self.messages:
                self.messages.append(deepcopy(messages))
                return {'tool_calls':[{'id':'read','function':{'name':'read_record','arguments':'{}'}}]}
            assert 'approved_order_count' in messages[-1]['content']
            return {'content':'系统没有已批准医嘱记录；在用药资料不等于已开药。'}
    api.app.dependency_overrides[get_llm]=lambda:QueryModel([])
    # Use one persistent fake client for this request's two reasoning steps.
    model=QueryModel([]);api.app.dependency_overrides[get_llm]=lambda:model
    response=api.post('/api/operations/assistant/medical',json={'resident_id':r['id'],'text':'3床的药开了吗？'})
    assert response.status_code==200,response.text
    assert response.json()['draft_created'] is False
    with factory() as db:assert db.scalar(select(func.count()).select_from(Draft))==0

def test_native_provider_sends_actual_tools_and_tool_choice(monkeypatch):
    import httpx
    from app.services.chat.llm import QwenClient
    from app.core.config import Settings
    from app.operations.function_calling import function_call
    from app.operations.react import Empty
    from app.operations import function_calling as provider
    requests=[];real_client=httpx.Client
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'id':'native','function':{'name':'read_record','arguments':'{}'}}]}}]})
    monkeypatch.setattr(provider.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    client=QwenClient(Settings(_env_file=None,llm_base_url='https://qwen.example.test',llm_api_key='only-test-key',llm_model='test-model'))
    tools=[{'type':'function','function':{'name':'read_record','parameters':Empty.model_json_schema()}}]
    result=function_call(client,[{'role':'user','content':'查状态'}],tools)
    assert result['tool_calls'][0]['function']['name']=='read_record'
    assert requests[0]['tools']==tools and requests[0]['tool_choice']=='auto'
    assert requests[0]['parallel_tool_calls'] is False and 'response_format' not in requests[0]
