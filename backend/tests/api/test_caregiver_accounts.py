from sqlalchemy import select
from app.models.resident import ResidentChange
from tests.api.test_residents import staff,payload

def test_caregiver_read_only_scope_and_revocation(client):
    api,_,_=client;admin=api.headers['Authorization'];first,token=staff(api);second,other=staff(api,'13912340002')
    row=api.post('/api/residents',json=payload(assigned_account_ids=[first])).json();key=row['id']
    api.headers['Authorization']=token
    assert api.get('/api/residents/'+key).status_code==200
    assert api.put('/api/residents/'+key,json=payload(version=1,change_reason='尝试编辑')).status_code==403
    assert api.put('/api/residents/'+key+'/care',json={'version':1,'change_reason':'尝试编辑','allergies':'','chronic_conditions':'','dietary_notes':'','mobility_notes':'','communication_notes':'','care_notes':'试图修改'}).status_code==403
    assert api.get('/api/residents/'+key).json()['care_notes']==''
    api.headers['Authorization']=other;assert api.get('/api/residents/'+key).status_code==404
    api.headers['Authorization']=admin
    assert api.put('/api/residents/'+key+'/assignments',json={'version':1,'account_ids':[second],'reason':'换班'}).status_code==200
    api.headers['Authorization']=token;assert api.get('/api/residents/'+key).status_code==404
    assert api.get('/api/residents').json()['total']==0

def test_registration_cannot_grant_admin_or_resident_access(client):
    api,_,_=client
    row=api.post('/api/residents',json=payload()).json()
    result=api.post('/api/auth/register',json={'phone':'13912340099','name':'新护工','password':'Care12345','role':'admin'})
    assert result.json()['role']=='user' and result.json()['status']=='pending'
    login=api.post('/api/auth/login',json={'phone':'13912340099','password':'Care12345'}).json();api.headers['Authorization']='Bearer '+login['token']
    assert api.get('/api/residents').status_code==403
    assert api.get('/api/residents/'+row['id']).status_code==403

def test_archive_edit_stays_in_administrative_console_not_caregiver(client):
    api,_,factory=client;admin=api.headers['Authorization'];sid,token=staff(api)
    row=api.post('/api/residents',json=payload(assigned_account_ids=[sid])).json()
    change=payload(name='核对姓名',contact_name='家属',assigned_account_ids=[sid],version=1,change_reason='管理员核对资料')
    api.headers['Authorization']=token;assert api.put('/api/residents/'+row['id'],json=change).status_code==403
    api.headers['Authorization']=admin;assert api.put('/api/residents/'+row['id'],json=change).status_code==200
    with factory() as db:
        assert db.scalar(select(ResidentChange).where(ResidentChange.reason=='管理员核对资料')).actor_name=='测试用户'
