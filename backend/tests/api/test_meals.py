from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4
from copy import deepcopy
import pytest
from app.services import meals
WEEK='2030-01-07'

@pytest.fixture(autouse=True)
def clock(monkeypatch):monkeypatch.setattr(meals,'now',lambda:datetime(2030,1,7,7,0,tzinfo=ZoneInfo('Asia/Shanghai')))

def menu_data():
    return {'week_start':WEEK,'version':0,'slots':[{'day':day,'meal':meal,'cutoff':'08:00','options':[
        {'id':str(uuid4()),'name':'鱼餐','foods':['米饭','清蒸鱼','蔬菜'],'ingredients':['大米','鱼','青菜'],'allergens':['鱼'],'tags':[],'texture':'normal','capacity':1,'notes':''},
        {'id':str(uuid4()),'name':'鸡肉餐','foods':['米饭','炖鸡肉','蔬菜'],'ingredients':['大米','鸡肉','青菜'],'allergens':[],'tags':[],'texture':'normal','capacity':10,'notes':''},
    ]} for day in range(7) for meal in ['breakfast','lunch','dinner']]}

def elder(api,phone):
    row=api.post('/api/residents',json={'name':'虚构老人'+phone[-2:],'source':'选餐测试'}).json()
    user=api.post('/api/auth/register',json={'phone':phone,'name':'老人','password':'MealTest123'}).json()
    assert api.put(f"/api/residents/{row['id']}/account-binding",json={'account_id':user['id'],'version':1,'reason':'测试核对'}).status_code==200
    token=api.post('/api/auth/login',json={'phone':phone,'password':'MealTest123'}).json()['token']
    return row['id'],'Bearer '+token

def profile(api,key,**updates):
    version=api.get('/api/residents/'+key).json()['version']
    data={'version':0,'resident_version':version,'allergy_status':'confirmed_none','confirmed':True,'allergens':[],'avoid_ingredients':[],'required_tags':[],'allowed_textures':['normal'],'source':'已核对入住资料（虚构测试）','notes':'',**updates}
    return api.put('/api/meals/profiles/'+key,json=data)

def save(api,data=None):
    r=api.put('/api/meals/menus',json=data or menu_data());assert r.status_code==200,r.text;return r.json()

def publish(api,menu,ack=False):return api.post(f"/api/meals/menus/{menu['id']}/publish",json={'version':menu['version'],'acknowledge_pending':ack})
def choose(api,menu,index=0,version=0):
    return api.put('/api/meals/mine',json={'menu_id':menu['id'],'day':0,'meal':'breakfast','option_id':menu['slots'][0]['options'][index]['id'],'version':version})

def test_full_week_selection_capacity_change_and_kitchen(client):
    api,_,_=client;admin=api.headers['Authorization']
    first,t1=elder(api,'13998760001');second,t2=elder(api,'13998760002')
    assert profile(api,first).status_code==200
    assert profile(api,second).status_code==200
    menu=save(api)
    api.headers['Authorization']=t1
    assert api.get('/api/meals/mine',params={'week_start':WEEK}).json()['menu'] is None
    api.headers['Authorization']=admin
    assert publish(api,menu).status_code==200
    api.headers['Authorization']=t1
    result=api.get('/api/meals/mine',params={'week_start':WEEK}).json()
    assert len(result['slots'])==21 and result['reviewed']
    assert choose(api,menu).status_code==200
    assert choose(api,menu).status_code==409
    api.headers['Authorization']=t2
    assert choose(api,menu).status_code==409
    api.headers['Authorization']=t1
    assert choose(api,menu,index=1,version=1).status_code==200
    api.headers['Authorization']=t2
    assert choose(api,menu).status_code==200
    api.headers['Authorization']=admin
    summary=api.get(f"/api/meals/menus/{menu['id']}/kitchen",params={'meal_date':WEEK,'meal':'breakfast'}).json()
    assert [o['count'] for o in summary['options']]==[1,1]
    assert summary['needs_review']==[] and summary['unselected']==[]


def test_pending_profiles_need_explicit_publish_ack_and_cannot_choose(client):
    api,_,_=client;admin=api.headers['Authorization']
    key,token=elder(api,'13998760003');menu=save(api)
    report=api.get(f"/api/meals/menus/{menu['id']}/coverage").json()
    assert len(report['pending'])==1 and report['reviewed_count']==0
    assert publish(api,menu).status_code==422
    assert publish(api,menu,True).status_code==200
    api.headers['Authorization']=token
    assert api.get('/api/meals/mine',params={'week_start':WEEK}).json()['reviewed'] is False
    assert choose(api,menu).status_code==409
    api.headers['Authorization']=admin
    assert profile(api,key,allergy_status='unknown').status_code==200
    api.headers['Authorization']=token
    assert choose(api,menu).status_code==409


def test_allergy_coverage_and_no_disease_inference(client):
    api,_,_=client;admin=api.headers['Authorization']
    key,token=elder(api,'13998760004')
    assert profile(api,key,allergy_status='known',allergens=['鱼']).status_code==200
    menu=save(api)
    assert publish(api,menu).status_code==200
    api.headers['Authorization']=token
    choices=api.get('/api/meals/mine',params={'week_start':WEEK}).json()['slots'][0]['options']
    assert choices[0]['reasons'] and choices[1]['reasons']==[]
    assert choose(api,menu).status_code==422
    assert choose(api,menu,index=1).status_code==200
    api.headers['Authorization']=admin
    assert profile(api,key,version=1,required_tags=['经确认的特殊要求']).status_code==200
    summary=api.get(f"/api/meals/menus/{menu['id']}/kitchen",params={'meal_date':WEEK,'meal':'breakfast'}).json()
    assert summary['needs_review'][0]['id']==key
    assert sum(o['count'] for o in summary['options'])==0


def test_publication_requires_options_for_reviewed_people_and_freezes_menu(client):
    api,_,_=client
    key,_=elder(api,'13998760005')
    assert profile(api,key,required_tags=['低盐']).status_code==200
    menu=save(api)
    response=publish(api,menu)
    assert response.status_code==422
    assert len(response.json()['detail']['coverage']['missing'])==21
    updated={**menu,'slots':deepcopy(menu['slots'])}
    for slot in updated['slots']:
        for option in slot['options']:option['tags']=['低盐']
    saved=api.put('/api/meals/menus',json={k:updated[k] for k in ['week_start','version','slots']}).json()
    assert publish(api,saved).status_code==200
    assert api.put('/api/meals/menus',json={k:saved[k] for k in ['week_start','version','slots']}).status_code==409


def test_expired_deadline_and_stale_health_block_selection(client,monkeypatch):
    api,_,_=client;admin=api.headers['Authorization']
    key,token=elder(api,'13998760006');assert profile(api,key).status_code==200
    menu=save(api);assert publish(api,menu).status_code==200
    api.headers['Authorization']=token
    monkeypatch.setattr(meals,'now',lambda:datetime(2030,1,7,8,0,tzinfo=ZoneInfo('Asia/Shanghai')))
    assert choose(api,menu).status_code==409
    monkeypatch.setattr(meals,'now',lambda:datetime(2030,1,7,7,0,tzinfo=ZoneInfo('Asia/Shanghai')))
    api.headers['Authorization']=admin
    assert api.put('/api/residents/'+key,json={'name':'虚构更正','source':'核对','version':2,'change_reason':'健康更新'}).status_code==200
    api.headers['Authorization']=token
    assert choose(api,menu).status_code==409


def test_roles_validation_and_foreign_option_rejected(client):
    api,_,_=client;admin=api.headers['Authorization']
    key,token=elder(api,'13998760007');assert profile(api,key).status_code==200
    bad=menu_data();bad['slots']=bad['slots'][:-1]
    assert api.put('/api/meals/menus',json=bad).status_code==422
    bad=menu_data();bad['week_start']='2030-01-08'
    assert api.put('/api/meals/menus',json=bad).status_code==422
    menu=save(api);assert publish(api,menu).status_code==200
    api.headers['Authorization']=token
    for path in ['/api/meals/requirements','/api/meals/menus?week_start='+WEEK,f"/api/meals/menus/{menu['id']}/coverage",f"/api/meals/menus/{menu['id']}/kitchen?meal_date={WEEK}&meal=breakfast"]:
        assert api.get(path).status_code==403
    assert api.put('/api/meals/mine',json={'menu_id':menu['id'],'day':0,'meal':'breakfast','option_id':str(uuid4()),'version':0}).status_code==422
    assert api.put('/api/meals/mine',json={'menu_id':menu['id'],'day':0,'meal':'breakfast','option_id':menu['slots'][0]['options'][0]['id'],'resident_id':key}).status_code==422
    api.headers['Authorization']=admin
    assert api.get('/api/meals/mine?week_start='+WEEK).status_code==403
    api.headers.pop('Authorization')
    assert api.get('/api/meals/mine?week_start='+WEEK).status_code==401


def test_discharged_orders_do_not_consume_in_care_capacity(client):
    api,_,_=client;admin=api.headers['Authorization']
    key,t1=elder(api,'13998760008');other,t2=elder(api,'13998760009')
    assert profile(api,key).status_code==200
    assert profile(api,other).status_code==200
    menu=save(api);assert publish(api,menu).status_code==200
    api.headers['Authorization']=t1;assert choose(api,menu).status_code==200
    api.headers['Authorization']=admin
    assert api.put('/api/residents/'+key,json={'name':'离院老人','source':'测试离院','status':'discharged','version':2,'change_reason':'办理离院'}).status_code==200
    api.headers['Authorization']=t2;assert choose(api,menu).status_code==200
    api.headers['Authorization']=t1;assert choose(api,menu,version=1).status_code==409
    api.headers['Authorization']=admin
    report=api.get(f"/api/meals/menus/{menu['id']}/kitchen",params={'meal_date':WEEK,'meal':'breakfast'}).json()
    assert report['in_care']==1 and report['options'][0]['count']==1
