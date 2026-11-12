from sqlalchemy import select
from app.models.resident import ResidentChange
from tests.api.test_residents import staff, payload


def care(row, **changes):
    return {**{key:row[key] for key in ('allergies','chronic_conditions','dietary_notes','mobility_notes','communication_notes','care_notes')},'version':row['version'],'change_reason':'巡查后核对',**changes}


def test_caregiver_scope_edit_and_revocation(client):
    api,_,factory=client
    admin=api.headers['Authorization']
    first,token=staff(api)
    second,other=staff(api,'13912340002')
    row=api.post('/api/residents',json=payload(assigned_account_ids=[first])).json()
    key=row['id']
    roster=api.get('/api/auth/caregivers').json()
    assert next(r for r in roster if r['id']==first)['resident_count']==1
    assert all('phone' not in r for r in roster)
    api.headers['Authorization']=other
    assert api.put(f'/api/residents/{key}/care',json=care(row)).status_code==404
    assert api.get('/api/auth/caregivers').status_code==403
    api.headers['Authorization']=token
    updated=api.put(f'/api/residents/{key}/care',json=care(row,care_notes='移位时需协助'))
    assert updated.status_code==200,updated.text
    assert updated.json()['version']==2
    assert updated.json()['assigned_account_ids']==[first]
    assert api.put(f'/api/residents/{key}/care',json=care(row)).status_code==409
    assert api.put(f'/api/residents/{key}/care',json=care(updated.json(),assigned_account_ids=[second])).status_code==422
    assert api.put(f'/api/residents/{key}/assignments',json={'version':2,'account_ids':[second],'reason':'换班'}).status_code==403
    api.headers['Authorization']=admin
    assert api.put(f'/api/residents/{key}/assignments',json={'version':1,'account_ids':[second],'reason':'旧页面'}).status_code==409
    result=api.put(f'/api/residents/{key}/assignments',json={'version':2,'account_ids':[second],'reason':'换班'})
    assert result.status_code==200,result.text
    assert result.json()['care_notes']=='移位时需协助'
    api.headers['Authorization']=token
    assert api.get('/api/residents').json()['total']==0
    assert api.put(f'/api/residents/{key}/care',json=care(result.json())).status_code==404
    api.headers['Authorization']=other
    assert api.get(f'/api/residents/{key}').status_code==200
    with factory() as db:
        audit=db.scalar(select(ResidentChange).where(ResidentChange.actor_id==first))
        assert audit.before['care_notes']==''
        assert audit.after['care_notes']=='移位时需协助'


def test_registration_cannot_grant_admin_or_resident_access(client):
    api,_,_=client
    row=api.post('/api/residents',json=payload()).json()
    result=api.post('/api/auth/register',json={'phone':'13912340099','name':'新护工','password':'Care12345','role':'admin'})
    assert result.json()['role']=='user'
    login=api.post('/api/auth/login',json={'phone':'13912340099','password':'Care12345'}).json()
    api.headers['Authorization']='Bearer '+login['token']
    assert api.get('/api/residents').json()['items']==[]
    assert api.get('/api/residents/'+row['id']).status_code==404
    assert api.get('/api/documents').status_code==403


def test_caregiver_can_edit_assigned_resident_full_information(client):
    api,_,_=client
    admin=api.headers['Authorization']
    first,token=staff(api)
    second,other=staff(api,'13912340002')
    row=api.post('/api/residents',json=payload(assigned_account_ids=[first])).json()
    key=row['id']
    api.headers['Authorization']=token
    change=payload(name='已核对姓名',contact_name='家属',contact_phone='13912345678',location='B楼201室',care_level='部分协助',dietary_notes='清淡软食',assigned_account_ids=[first],version=1,change_reason='核对入住资料')
    result=api.put('/api/residents/'+key,json=change)
    assert result.status_code==200,result.text
    assert result.json()['name']=='已核对姓名'
    assert result.json()['contact_name']=='家属'
    assert result.json()['dietary_notes']=='清淡软食'
    assert result.json()['version']==2
    assert api.put('/api/residents/'+key,json={**change,'version':2,'assigned_account_ids':[first,second]}).status_code==403
    api.headers['Authorization']=other
    assert api.put('/api/residents/'+key,json={**change,'version':2}).status_code==404
    api.headers['Authorization']=admin
    history=api.get(f'/api/residents/{key}/changes').json()['items']
    assert any(item['reason']=='核对入住资料' and item['actor_name']=='护理员' for item in history)
