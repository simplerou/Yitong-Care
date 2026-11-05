import pytest
from copy import deepcopy
from datetime import date
import json
from uuid import uuid4
from sqlalchemy import select,func
from app.models.meals import WeeklyMenu,MealProfile,MealChange
from app.services.chat.llm import get_menu_llm
from app.core.exceptions import BusinessError

@pytest.fixture(autouse=True)
def isolate_external_recipe_service(monkeypatch):
    # Local .env may enable a real service; automated planner tests must stay offline.
    monkeypatch.setattr('app.agents.menu_planner.candidates',lambda **kwargs:{'status':'disabled','provider':'HowToCook MCP','recipes':[],'count':0})

WEEK='2030-01-14'
class FakePlanner:
    model='fake-menu-model'
    def __init__(self,mode='normal',callback=None):self.calls=[];self.mode=mode;self.callback=callback
    def ensure_configured(self):pass
    def complete_json(self,system,payload,max_tokens=1800):
        self.calls.append(deepcopy(payload))
        if self.callback and len(self.calls)==1:self.callback()
        if self.mode=='timeout':raise BusinessError('模拟模型超时',504)
        if self.mode=='always_bad' or (self.mode=='repair_once' and len(self.calls)==1):return {'slots':[]}
        if self.mode=='repair_daily' and 'repair' not in payload:return {'slots':[]}
        groups=payload['requirements']['groups']
        blocked={v for g in groups for k in ['allergens','avoid_ingredients'] for v in g['requirements'][k]}
        ingredients=[v for v in ['大米','鸡肉','青菜','食盐','食用油'] if v not in blocked]
        if self.mode=='wrong_stock':ingredients=['清单外食材']
        tags=sorted({v for g in groups for v in g['requirements']['required_tags']})
        slots=[]
        for meal in ['breakfast','lunch','dinner']:
            options=[]
            for i in range(payload['options_per_meal']):
                texture=groups[i%len(groups)]['requirements']['allowed_textures'][0] if groups else 'normal'
                if self.mode=='uncovered':texture='pureed'
                options.append({'name':f'第{payload["day"]+1}天方案{i+1}','foods':[f'{meal}主食{i+1}','炖鸡肉','青菜'],'ingredients':ingredients,'allergens':[],'tags':tags,'texture':texture,'notes':'人工核对制作方法'})
            slots.append({'meal':meal,'options':options})
        return {'slots':slots}


def requirement(api,phone='13911220001',name='隐私老人甲',reviewed=True):
    row=api.post('/api/residents',json={'name':name,'source':'PRIVATE_RESIDENT_SOURCE','allergies':'PRIVATE_RAW_HEALTH','chronic_conditions':'PRIVATE_CHRONIC','contact_phone':phone,'location':'PRIVATE_LOCATION'}).json()
    if reviewed:
        r=api.put('/api/meals/profiles/'+row['id'],json={'version':0,'resident_version':1,'allergy_status':'known','confirmed':True,'allergens':['鱼'],'avoid_ingredients':[],'required_tags':['低盐'],'allowed_textures':['normal'],'source':'PRIVATE_PROFILE_SOURCE','notes':'PRIVATE_PROFILE_NOTES'})
        assert r.status_code==200,r.text
    return row

def setup_llm(api,llm):api.app.dependency_overrides[get_menu_llm]=lambda:llm

def request(**values):return {'week_start':WEEK,'version':0,'options_per_meal':2,**values}


def test_generate_week_is_private_validated_and_not_saved_or_published(client):
    api,_,factory=client
    one=requirement(api);two=requirement(api,'13911220002','隐私老人乙')
    llm=FakePlanner();setup_llm(api,llm)
    response=api.post('/api/meals/generate',json=request())
    assert response.status_code==200,response.text
    body=response.json()
    assert body['saved'] is False and body['published'] is False
    assert body['menu']['status']=='draft' and len(body['menu']['slots'])==21
    assert len({o['id'] for s in body['menu']['slots'] for o in s['options']})==42
    assert body['summary']=={'in_care':2,'reviewed_count':2,'pending_count':0}
    assert body['coverage']['missing']==[]
    assert len(llm.calls)==14 and body['metrics']['llm_calls']==14
    assert any('diversity_suggestions' in call.get('repair',{}) for call in llm.calls)
    assert any('菜品丰富度' in warning for warning in body['warnings'])
    assert len(llm.calls[0]['requirements']['groups'])==1
    assert llm.calls[0]['requirements']['groups'][0]['count']==2
    payloads=json.dumps(llm.calls,ensure_ascii=False)
    for secret in [one['id'],two['id'],one['record_no'],one['name'],two['name'],'13911220001','PRIVATE_RESIDENT_SOURCE','PRIVATE_RAW_HEALTH','PRIVATE_PROFILE_SOURCE','PRIVATE_PROFILE_NOTES','PRIVATE_LOCATION','PRIVATE_CHRONIC']:
        assert secret not in payloads
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(WeeklyMenu))==0
        assert db.scalar(select(func.count()).select_from(MealChange).where(MealChange.kind=='menu_ai_preview'))==1
    # Existing save and publish remain explicit administrator actions.
    candidate={k:body['menu'][k] for k in ['week_start','version','slots']}
    saved=api.put('/api/meals/menus',json=candidate)
    assert saved.status_code==200,saved.text
    assert saved.json()['status']=='draft'


def test_pending_is_not_treated_as_healthy(client):
    api,_,_=client;requirement(api,reviewed=False)
    llm=FakePlanner();setup_llm(api,llm)
    assert api.post('/api/meals/generate',json=request()).status_code==422
    assert llm.calls==[]
    r=api.post('/api/meals/generate',json=request(acknowledge_pending=True))
    assert r.status_code==200,r.text
    assert r.json()['summary']['pending_count']==1
    assert llm.calls[0]['requirements']['groups']==[]
    assert r.json()['coverage']['reviewed_count']==0
    assert any('待核实' in v for v in r.json()['warnings'])


def test_bounded_repairs_and_failure_preserve_database(client):
    api,_,factory=client;requirement(api)
    llm=FakePlanner('repair_daily');setup_llm(api,llm)
    r=api.post('/api/meals/generate',json=request())
    assert r.status_code==200,r.text
    assert len(llm.calls)==14 and r.json()['repairs']==7
    assert 'repair' in llm.calls[1]
    llm=FakePlanner('always_bad');setup_llm(api,llm)
    assert api.post('/api/meals/generate',json=request()).status_code==502
    assert len(llm.calls)==2
    with factory() as db:assert db.scalar(select(func.count()).select_from(WeeklyMenu))==0


def test_inventory_violation_rejected_and_missing_coverage_remains_draft(client):
    api,_,_=client;requirement(api)
    llm=FakePlanner('wrong_stock');setup_llm(api,llm)
    assert api.post('/api/meals/generate',json=request(available_ingredients=['大米','鸡肉','青菜','食盐','食用油'])).status_code==502
    assert len(llm.calls)==2
    llm=FakePlanner('uncovered');setup_llm(api,llm)
    r=api.post('/api/meals/generate',json=request())
    assert r.status_code==200,r.text
    assert len(llm.calls)==14 and len(r.json()['coverage']['missing'])==21
    assert r.json()['menu']['status']=='draft'
    assert any('替代餐' in text for text in r.json()['warnings'])


def test_access_config_validation_and_upstream_error(client):
    api,_,_=client;requirement(api)
    llm=FakePlanner('timeout');setup_llm(api,llm)
    assert api.post('/api/meals/generate',json=request(week_start='2030-01-15')).status_code==422
    assert api.post('/api/meals/generate',json=request(options_per_meal=5)).status_code==422
    assert api.post('/api/meals/generate',json=request()).status_code==504
    assert len(llm.calls)==1
    token=api.post('/api/auth/register',json={'phone':'13911220003','name':'普通用户','password':'Planner123'}).json()
    token=api.post('/api/auth/login',json={'phone':'13911220003','password':'Planner123'}).json()['token']
    api.headers['Authorization']='Bearer '+token
    assert api.post('/api/meals/generate',json=request()).status_code==403
    api.headers.pop('Authorization')
    assert api.post('/api/meals/generate',json=request()).status_code==401
    assert len(llm.calls)==1


def test_generation_conflict_and_changed_requirements_are_rechecked(client):
    api,_,factory=client;one=requirement(api)
    llm=FakePlanner();setup_llm(api,llm)
    result=api.post('/api/meals/generate',json=request()).json()
    payload={k:result['menu'][k] for k in ['week_start','version','slots']}
    saved=api.put('/api/meals/menus',json=payload).json()
    assert api.post('/api/meals/generate',json=request()).status_code==409
    def change_menu():
        with factory() as db:
            row=db.get(WeeklyMenu,saved['id']);row.version+=1;db.commit()
    llm=FakePlanner(callback=change_menu);setup_llm(api,llm)
    assert api.post('/api/meals/generate',json=request(version=1)).status_code==409
    def change_profile():
        with factory() as db:
            row=db.get(MealProfile,one['id']);row.version+=1;row.data={**row.data,'allowed_textures':['soft']};db.commit()
    llm=FakePlanner(callback=change_profile);setup_llm(api,llm)
    r=api.post('/api/meals/generate',json=request(version=2))
    assert r.status_code==200,r.text
    assert r.json()['context_changed'] is True and len(r.json()['coverage']['missing'])==21
    with factory() as db:assert db.get(WeeklyMenu,saved['id']).version==2


def test_previous_week_is_used_and_published_target_rejected(client):
    api,_,_=client;requirement(api)
    llm=FakePlanner();setup_llm(api,llm)
    body=api.post('/api/meals/generate',json=request(week_start='2030-01-07')).json()
    saved=api.put('/api/meals/menus',json={k:body['menu'][k] for k in ['week_start','version','slots']}).json()
    assert api.post(f"/api/meals/menus/{saved['id']}/publish",json={'version':saved['version']}).status_code==200
    count=len(llm.calls)
    assert api.post('/api/meals/generate',json=request(week_start='2030-01-07',version=2)).status_code==409
    assert len(llm.calls)==count
    llm=FakePlanner();setup_llm(api,llm)
    result=api.post('/api/meals/generate',json=request())
    assert result.status_code==200,result.text
    assert len(llm.calls[0]['previous_same_day'])==3
    assert result.json()['repetition']['previous_available'] is True
    assert result.json()['repetition']['same_as_previous']>0
    assert any('上周' in v for v in result.json()['warnings'])


def test_checks_reject_hidden_allergen_and_unsupported_claims():
    from app.schemas.meals import PlannedDay,GenerateMenuInput
    from app.services.menu_planning import check_day,summarize
    summary={'in_care':1,'reviewed_count':1,'pending_count':0,'groups':[{'group':'G001','count':1,'requirements':{'allergens':['鱼'],'avoid_ingredients':[],'required_tags':[],'allowed_textures':['normal']}}]}
    fake=FakePlanner()
    raw=fake.complete_json('',{'requirements':summary,'options_per_meal':2,'day':0})
    raw['slots'][0]['options'][0]['foods']=['清蒸鱼','米饭']
    raw['slots'][0]['options'][0]['ingredients']=['大米']
    raw['slots'][1]['options'][0]['notes']='保证降糖，蛋白质25克'
    hard,_=check_day(PlannedDay.model_validate(raw),summary,GenerateMenuInput(week_start=WEEK))
    assert any('未声明' in issue for issue in hard)
    assert any('营养' in issue for issue in hard)
    raw['slots'][1]['options'][0]['notes']='本菜单不保证疗效，仅作饮食参考。'
    hard,_=check_day(PlannedDay.model_validate(raw),summary,GenerateMenuInput(week_start=WEEK))
    assert not any('营养' in issue for issue in hard)
    raw['slots'][1]['options'][0]['notes']='本菜单不保证疗效，但保证降糖'
    hard,_=check_day(PlannedDay.model_validate(raw),summary,GenerateMenuInput(week_start=WEEK))
    assert any('营养' in issue for issue in hard)

    # Preserve combinations (same allergy, different textures), not only marginal counts.
    base={'version':1,'allergens':['鱼'],'avoid_ingredients':[],'required_tags':[],'allowed_textures':['normal']}
    grouped,_=summarize([{'id':'private-a','resident_version':1,'reviewed':True,'profile':base},{'id':'private-b','resident_version':1,'reviewed':True,'profile':{**base,'allowed_textures':['soft']}}])
    assert len(grouped['groups'])==2 and sum(g['count'] for g in grouped['groups'])==2
    assert 'private-a' not in json.dumps(grouped)



def test_common_kitchen_tags_and_exact_chinese_enums_do_not_abort_generation(client):
    api,_,_=client;requirement(api,reviewed=False)
    class CommonTags(FakePlanner):
        def complete_json(self,system,payload,max_tokens=1800):
            raw=super().complete_json(system,payload,max_tokens=max_tokens)
            for slot in raw['slots']:
                slot['meal']=' '+{'breakfast':'早餐','lunch':'午餐','dinner':'晚餐'}[slot['meal']]+' '
                for option in slot['options']:
                    option['tags']=['少油','少盐','易消化'];option['texture']='普通质地 '
            return raw
    llm=CommonTags();setup_llm(api,llm)
    response=api.post('/api/meals/generate',json=request(acknowledge_pending=True,kitchen_notes='少油少盐，蒸炖为主',season='秋冬季',capacity_per_option=10))
    assert response.status_code==200,response.text
    body=response.json()
    assert len(llm.calls)==14 and body['repairs']==7
    assert body['normalizations']
    assert all(option['tags']==[] for slot in body['menu']['slots'] for option in slot['options'])
    assert body['coverage']['pending'] and body['saved'] is False
    assert any('未核实的通用标签' in warning for warning in body['warnings'])


def test_normalization_never_fabricates_required_tags_or_allergy_fields():
    from app.services.menu_planning import normalize_day,check_day
    from app.schemas.meals import PlannedDay,GenerateMenuInput
    summary={'groups':[{'group':'G001','count':1,'requirements':{'allergens':['鱼'],'avoid_ingredients':[],'required_tags':['低盐'],'allowed_textures':['normal']}}]}
    raw=FakePlanner().complete_json('',{'requirements':summary,'options_per_meal':2,'day':0})
    for slot in raw['slots']:
        for option in slot['options']:option['tags']=['少盐','易消化']
    normalized,changes=normalize_day(raw,summary)
    assert raw['slots'][0]['options'][0]['tags']==['少盐','易消化']
    planned=PlannedDay.model_validate(normalized)
    hard,missing=check_day(planned,summary,GenerateMenuInput(week_start=WEEK))
    assert not hard and len(missing)==3
    assert all(o.tags==[] for s in planned.slots for o in s.options)
    del raw['slots'][0]['options'][0]['allergens']
    normalized,_=normalize_day(raw,summary)
    assert 'allergens' not in normalized['slots'][0]['options'][0]


def test_failure_reports_exact_issues_and_saves_private_diagnostic(client):
    import stat
    from app.services.menu_diagnostics import get_menu_diagnostic_dir
    api,_,factory=client;one=requirement(api)
    llm=FakePlanner('wrong_stock');setup_llm(api,llm)
    response=api.post('/api/meals/generate',json=request(available_ingredients=['大米']))
    assert response.status_code==502
    message=response.json()['detail']
    assert '超出采购清单' in message and '清单外食材' in message and '诊断编号' in message
    root=api.app.dependency_overrides[get_menu_diagnostic_dir]()
    files=list(root.glob('menu-*.json'))
    assert len(files)==1
    assert stat.S_IMODE(files[0].stat().st_mode)==0o600
    body=json.loads(files[0].read_text())
    assert body['day']==1 and len(body['attempts'])==2
    assert body['issues'] and body['attempts'][-1]['candidate']
    raw=json.dumps(body,ensure_ascii=False)
    for secret in [one['id'],one['name'],'13911220001','PRIVATE_RESIDENT_SOURCE','PRIVATE_LOCATION','PRIVATE_CHRONIC']:
        assert secret not in raw
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(WeeklyMenu))==0

def test_howtocook_candidates_feed_planner_without_replacing_review_flow(client,monkeypatch):
    import app.agents.menu_planner as planner
    api,_,_=client
    requirement(api)
    context={'status':'success','provider':'HowToCook MCP','count':1,'recipes':[{'id':'recipe-1','name':'清蒸南瓜','ingredients':['南瓜'],'steps':['蒸熟'],'source_url':None}]}
    monkeypatch.setattr(planner,'candidates',lambda **kwargs:context)
    llm=FakePlanner();setup_llm(api,llm)
    response=api.post('/api/meals/generate',json=request())
    assert response.status_code==200,response.text
    assert response.json()['recipe_reference']==context
    assert response.json()['saved'] is False and response.json()['published'] is False
    assert all(call['external_recipe_candidates']==context['recipes'] for call in llm.calls)


def test_howtocook_failure_stops_before_model_and_keeps_menu_unsaved(client,monkeypatch):
    import app.agents.menu_planner as planner
    api,_,factory=client
    requirement(api)
    def fail(**kwargs):raise BusinessError('HowToCook 菜谱查询失败',502)
    monkeypatch.setattr(planner,'candidates',fail)
    llm=FakePlanner();setup_llm(api,llm)
    response=api.post('/api/meals/generate',json=request())
    assert response.status_code==502
    assert not llm.calls
    with factory() as db:assert db.scalar(select(func.count()).select_from(WeeklyMenu))==0
