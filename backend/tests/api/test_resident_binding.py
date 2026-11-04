from sqlalchemy import select, func
from app.models.resident import ResidentChange, ResidentAccountBinding
from app.models.auth import Account


def account(api,phone,name='老人账号'):
    assert api.post('/api/auth/register',json={'phone':phone,'name':name,'password':'Binding123'}).status_code==201
    return login(api,phone)


def login(api,phone):
    result=api.post('/api/auth/login',json={'phone':phone,'password':'Binding123'}).json()
    return result['user'],'Bearer '+result['token']


def resident(api,name='张阿姨',**kwargs):
    result=api.post('/api/residents',json={'name':name,'source':'虚构绑定测试','allergies':'虚构过敏记录',**kwargs})
    assert result.status_code==201,result.text
    return result.json()


def bind(api,row,user,version=1,**extra):
    return api.put(f"/api/residents/{row['id']}/account-binding",json={'account_id':user['id'] if user else None,'version':version,'reason':'线下核对本人身份',**extra})


def test_bind_read_own_only_and_revoke_on_unbind(client):
    api,_,factory=client;admin=api.headers['Authorization']
    one=resident(api);two=resident(api,'另一位老人')
    user,oldtoken=account(api,'13943210001')
    assert bind(api,one,user).status_code==200
    api.headers['Authorization']=oldtoken
    assert api.get('/api/auth/me').status_code==401
    user,token=login(api,'13943210001');assert user['role']=='resident'
    api.headers['Authorization']=token
    mine=api.get('/api/residents/me').json()['resident']
    assert mine['id']==one['id'] and mine['allergies']=='虚构过敏记录'
    assert 'assigned_account_ids' not in mine and 'source' not in mine and 'contact_phone' not in mine
    assert api.get('/api/residents/me',params={'resident_id':two['id']}).json()['resident']['id']==one['id']
    for path in ['/api/residents','/api/residents/'+one['id'],'/api/residents/'+two['id'],'/api/residents/assignees','/api/residents/bindable-accounts']:
        assert api.get(path).status_code==403,path
    assert bind(api,two,user).status_code==403
    assert api.get('/api/documents').status_code==403
    api.headers['Authorization']=admin
    assert bind(api,one,None,version=2).status_code==200
    api.headers['Authorization']=token
    assert api.get('/api/residents/me').status_code==401
    user,token=login(api,'13943210001');assert user['role']=='resident'
    api.headers['Authorization']=token
    assert api.get('/api/residents/me').json()=={'resident':None}
    assert api.get('/api/residents').status_code==403
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ResidentAccountBinding))==0
        assert db.scalar(select(func.count()).select_from(ResidentChange).where(ResidentChange.resident_id==one['id']))==3


def test_unique_binding_replacement_and_version_control(client):
    api,_,factory=client;admin=api.headers['Authorization']
    one=resident(api);two=resident(api,'李叔叔')
    user,oldtoken=account(api,'13943210002')
    other,otherold=account(api,'13943210003')
    assert bind(api,one,user).status_code==200
    assert bind(api,two,user).status_code==409
    assert bind(api,one,other,version=1).status_code==409
    assert bind(api,one,other,version=2).status_code==200
    assert api.get(f"/api/residents/{one['id']}/account-binding").json()['account']['id']==other['id']
    assert api.get('/api/residents/'+one['id']).json()['version']==3
    with factory() as db:
        assert db.get(Account,user['id']).role=='resident'
        assert db.get(Account,other['id']).role=='resident'
    user,token=login(api,'13943210002');api.headers['Authorization']=token
    assert api.get('/api/residents/me').json()['resident'] is None
    other,token=login(api,'13943210003');api.headers['Authorization']=token
    assert api.get('/api/residents/me').json()['resident']['id']==one['id']


def test_admin_and_assigned_workers_cannot_be_bound(client):
    api,_,factory=client
    row=resident(api)
    with factory() as db:admin=db.scalar(select(Account).where(Account.role=='admin'));admin_id=admin.id
    assert bind(api,row,{'id':admin_id}).status_code==422
    worker,_=account(api,'13943210004','工作人员')
    assigned=resident(api,'负责的老人',assigned_account_ids=[worker['id']])
    assert bind(api,row,worker).status_code==409
    candidates=api.get('/api/residents/bindable-accounts').json()['items']
    assert not any(item['id'] in [worker['id'],admin_id] for item in candidates)
    assert api.get('/api/residents/'+row['id']).json()['version']==1


def test_candidate_privacy_self_claim_denied_and_resident_not_assignable(client):
    api,_,_=client;admin=api.headers['Authorization']
    row=resident(api)
    user,token=account(api,'13943210005')
    results=api.get('/api/residents/bindable-accounts',params={'q':'13943210005'}).json()['items']
    assert len(results)==1 and results[0]['phone_hint']=='139****0005'
    assert 'phone' not in results[0]
    api.headers['Authorization']=token
    assert bind(api,row,user).status_code==403
    assert api.get('/api/residents/me').status_code==403
    api.headers['Authorization']=admin
    assert bind(api,row,user,reason=' ').status_code==422
    assert bind(api,row,user).status_code==200
    assert api.get('/api/residents/bindable-accounts',params={'q':'13943210005'}).json()['items']==[]
    assert api.post('/api/residents',json={'name':'另一人','source':'测试','assigned_account_ids':[user['id']]}).status_code==422


def test_binding_is_audited_and_noop_does_not_revoke_again(client):
    api,_,factory=client
    row=resident(api);user,_=account(api,'13943210006')
    assert bind(api,row,user).json()['version']==2
    assert bind(api,row,user,version=2).json()['version']==2
    with factory() as db:
        logs=db.scalars(select(ResidentChange).where(ResidentChange.resident_id==row['id'])).all()
        assert len(logs)==2
        log=next(item for item in logs if '绑定' in item.reason)
        assert log.before['bound_account_id'] is None
        assert log.after['bound_account_id']==user['id']
