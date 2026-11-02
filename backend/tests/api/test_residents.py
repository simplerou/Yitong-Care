from uuid import uuid4
from sqlalchemy import select
from app.models.resident import Resident, ResidentChange
from app.models.auth import Account


def staff(api, phone='13912340001'):
    assert api.post('/api/auth/register',json={'phone':phone,'name':'护理员','password':'Care12345'}).status_code==201
    result=api.post('/api/auth/login',json={'phone':phone,'password':'Care12345'}).json()
    return result['user']['id'],'Bearer '+result['token']


def payload(**updates):
    return {'name':'测试老人','source':'家属提供的入住资料',**updates}


def test_create_read_update_and_history(client):
    api,_,factory=client
    response=api.post('/api/residents',json=payload(birth_date='1945-02-01',location='201 / 02床'))
    assert response.status_code==201,response.text
    row=response.json();key=row['id']
    assert row['record_no'].startswith('R')
    assert row['allergies']=='' and row['care_level']=='未评估'
    assert api.get('/api/residents').json()['total']==1
    assert api.get('/api/residents?q=201').json()['total']==1
    assert api.get('/api/residents?q=%25').json()['total']==0
    assert api.get('/api/residents/'+key).json()['birth_date']=='1945-02-01'
    updated=api.put('/api/residents/'+key,json=payload(name='测试老人更正',version=1,change_reason='核对姓名'))
    assert updated.status_code==200,updated.text
    assert updated.json()['version']==2
    assert api.put('/api/residents/'+key,json=payload(version=1,change_reason='旧页面')).status_code==409
    history=api.get(f'/api/residents/{key}/changes').json()['items']
    assert len(history)==2
    with factory() as db:
        rows=db.scalars(select(ResidentChange).where(ResidentChange.resident_id==key)).all()
        edit=next(row for row in rows if row.reason=='核对姓名')
        assert edit.before['name']=='测试老人'
        assert edit.after['name']=='测试老人更正'
        assert edit.actor_name=='测试用户'
    # Discharge retains the record and its history; there is no destructive delete API.
    assert api.put('/api/residents/'+key,json=payload(version=2,change_reason='出院',status='discharged')).status_code==200
    assert api.get('/api/residents?status=in_care').json()['total']==0
    assert api.get('/api/residents?status=discharged').json()['total']==1


def test_assignment_is_checked_on_every_request_and_cannot_be_self_granted(client):
    api,_,_=client
    admin=api.headers['Authorization']
    sid,token=staff(api)
    other,other_token=staff(api,'13912340002')
    options=api.get('/api/residents/assignees')
    assert options.status_code==200
    assert all('phone' not in row for row in options.json())
    created=api.post('/api/residents',json=payload(assigned_account_ids=[sid])).json()
    key=created['id']
    api.headers['Authorization']=other_token
    assert api.get('/api/residents').json()['total']==0
    assert api.get('/api/residents/'+key).status_code==404
    assert api.get('/api/residents/'+str(uuid4())).status_code==404
    api.headers['Authorization']=token
    assert api.get('/api/residents').json()['total']==1
    assert api.get('/api/residents/'+key).status_code==200
    assert api.post('/api/residents',json=payload()).status_code==403
    assert api.put('/api/residents/'+key,json=payload(version=1,change_reason='绕过')).status_code==403
    assert api.get('/api/residents/assignees').status_code==403
    assert api.get('/api/residents/'+key+'/changes').status_code==403
    api.headers['Authorization']=admin
    assert api.put('/api/residents/'+key,json=payload(version=1,change_reason='变更负责人员',assigned_account_ids=[other])).status_code==200
    api.headers['Authorization']=token
    assert api.get('/api/residents/'+key).status_code==404
    assert api.get('/api/residents').json()['items']==[]
    api.headers['Authorization']=other_token
    assert api.get('/api/residents/'+key).status_code==200


def test_validation_and_no_partial_writes(client):
    api,_,factory=client
    for data in [payload(name=' '),payload(source=''),payload(birth_date='2999-01-01'),payload(birth_date='1950-01-01',admission_date='1940-01-01'),payload(contact_phone='abc'),payload(assigned_account_ids=[str(uuid4())]),payload(assigned_account_ids=['a','a'])]:
        assert api.post('/api/residents',json=data).status_code==422,data
    assert api.get('/api/residents').json()['total']==0
    with factory() as db:
        admin=db.scalar(select(Account).where(Account.role=='admin'))
        assert api.post('/api/residents',json=payload(assigned_account_ids=[admin.id])).status_code==422
    row=api.post('/api/residents',json=payload()).json()
    assert api.put('/api/residents/'+row['id'],json=payload(version=1,change_reason='  ')).status_code==422
    assert api.get('/api/residents/'+row['id']).json()['version']==1
    assert len(api.get('/api/residents/'+row['id']+'/changes').json()['items'])==1


def test_anonymous_denied_and_second_admin_can_manage(client):
    api,_,factory=client
    original=api.headers.pop('Authorization')
    assert api.get('/api/residents').status_code==401
    assert api.post('/api/residents',json=payload()).status_code==401
    api.headers['Authorization']=original
    row=api.post('/api/residents',json=payload()).json()
    sid,token=staff(api)
    with factory() as db:
        db.get(Account,sid).role='admin';db.commit()
    api.headers['Authorization']=token
    assert api.get('/api/residents/'+row['id']).status_code==200
    assert api.put('/api/residents/'+row['id'],json=payload(version=1,change_reason='管理员交接')).status_code==200
