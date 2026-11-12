from app.models.auth import Account
from sqlalchemy import select

def register(api,role='user',phone='13977770001'):
    return api.post('/api/auth/register',json={'name':'新员工','phone':phone,'password':'Staff12345','requested_role':role,'application_note':'入职核对'})
def login(api,phone='13977770001'):
    response=api.post('/api/auth/login',json={'phone':phone,'password':'Staff12345'})
    if response.status_code==200:api.headers['Authorization']='Bearer '+response.json()['token']
    return response

def test_new_registration_is_pending_for_all_roles_and_cannot_access_business(client):
    api,_,_=client;admin=api.headers['Authorization']
    for n,role in enumerate(['user','medical','kitchen','nursing','finance']):
        phone=f'1397777000{n}';response=register(api,role,phone)
        assert response.status_code==201,response.text
        assert response.json()['status']=='pending' and response.json()['role']=='user'
        login(api,phone)
        assert api.get('/api/auth/me').json()['requested_role']==role
        for path in ['/api/residents','/api/documents','/api/operations/identity','/api/account-reviews']:
            assert api.get(path).status_code==403,path
        api.headers['Authorization']=admin
    assert api.get('/api/auth/caregivers').json()==[]
    assert register(api,'admin','13977770999').status_code==422

def test_professional_review_session_revocation_and_idempotency(client):
    api,_,_=client;admin=api.headers['Authorization'];user=register(api,'medical').json();login(api);old=api.headers['Authorization']
    assert api.post(f"/api/account-reviews/{user['id']}/decision",json={'version':1,'action':'approve'}).status_code==403
    api.headers['Authorization']=admin
    assert api.put('/api/operations/staff',json={'account_id':user['id'],'role':'kitchen'}).status_code==409
    data={'version':1,'action':'approve','role':'medical'}
    assert api.post(f"/api/account-reviews/{user['id']}/decision",json=data).status_code==422
    data.update(qualification='线下核实医师任职记录',valid_until='2099-01-01',note='已核实')
    response=api.post(f"/api/account-reviews/{user['id']}/decision",json=data);assert response.status_code==200,response.text
    assert api.post(f"/api/account-reviews/{user['id']}/decision",json=data).json()['application_version']==2
    api.headers['Authorization']=old;assert api.get('/api/auth/me').status_code==401
    assert login(api).json()['user']['role']=='medical'
    assert api.get('/api/operations/identity').json()['qualified'] is True

def test_rejection_reason_resubmit_and_adjusted_role(client):
    api,_,_=client;admin=api.headers['Authorization'];user=register(api,'nursing').json()
    path=f"/api/account-reviews/{user['id']}/decision"
    assert api.post(path,json={'version':1,'action':'reject','note':' '}).status_code==422
    assert api.post(path,json={'version':1,'action':'reject','note':'请补充任职安排'}).status_code==200
    login(api)
    assert api.get('/api/auth/me').json()['review_note']=='请补充任职安排'
    assert api.put('/api/auth/application',json={'version':1,'requested_role':'kitchen'}).status_code==409
    result=api.put('/api/auth/application',json={'version':2,'requested_role':'kitchen','application_note':'补充说明'})
    assert result.json()['status']=='pending' and result.json()['application_version']==3
    assert api.get('/api/residents').status_code==403
    api.headers['Authorization']=admin
    assert api.post(path,json={'version':1,'action':'approve','role':'user'}).status_code==409
    assert api.post(path,json={'version':3,'action':'approve','role':'user'}).status_code==200
    login(api);assert api.get('/api/residents').json()['total']==0
    assert api.put('/api/auth/application',json={'version':4,'requested_role':'finance'}).status_code==409

def test_disable_restore_and_last_admin_guard(client):
    api,_,factory=client;admin=api.headers['Authorization'];user=register(api).json();path=f"/api/account-reviews/{user['id']}"
    assert api.post(path+'/decision',json={'version':1,'action':'approve','role':'user'}).status_code==200
    login(api);old=api.headers['Authorization'];api.headers['Authorization']=admin
    result=api.put(path+'/status',json={'version':2,'status':'disabled','note':'离职停用'});assert result.status_code==200,result.text
    api.headers['Authorization']=old;assert api.get('/api/auth/me').status_code==401
    assert login(api).status_code==403
    api.headers['Authorization']=admin
    assert api.put(path+'/status',json={'version':3,'status':'active','note':'重新入职'}).status_code==200
    assert login(api).status_code==200
    api.headers['Authorization']=admin
    with factory() as db:
        director=db.scalar(select(Account).where(Account.role=='admin'))
        assert director.status=='active'
        result=api.put(f'/api/account-reviews/{director.id}/status',json={'version':director.application_version,'status':'disabled','note':'尝试停用'})
        assert result.status_code==409
