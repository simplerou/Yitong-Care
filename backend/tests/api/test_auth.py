from datetime import timedelta
from sqlalchemy import select
from app.models.auth import Account, LoginSession
from app.core.auth import now

def test_anonymous_business_endpoints_rejected(client):
    api, _, _ = client
    api.headers.pop('Authorization')
    for method, path in [('GET','/api/documents'),('GET','/api/knowledge-bases'),('POST','/api/documents'),('GET','/api/agents/policy/config')]:
        assert api.request(method,path).status_code == 401

def test_register_login_wrong_password_and_logout(client):
    api, _, factory = client
    api.headers.pop('Authorization')
    data = {'phone':'13900000000','name':'测试','password':'Strong123'}
    assert api.post('/api/auth/register',json=data).status_code == 201
    assert api.post('/api/auth/register',json=data).status_code == 409
    assert api.post('/api/auth/login',json={**data,'password':'wrong'}).status_code == 401
    assert api.post('/api/auth/register',json={**data,'phone':'13700000000','password':'weakonly'}).status_code == 422
    response = api.post('/api/auth/login',json=data)
    assert response.status_code == 200
    token = response.json()['token']
    api.headers['Authorization'] = 'Bearer '+token
    assert api.get('/api/auth/me').json()['name'] == '测试'
    assert api.get('/api/documents').status_code == 403
    with factory() as db:
        account = db.scalar(select(Account).where(Account.phone==data['phone']))
        assert account.password_hash != data['password']
        assert db.scalar(select(LoginSession).where(LoginSession.account_id==account.id)).token_hash != token
    assert api.post('/api/auth/logout').status_code == 204
    assert api.get('/api/documents').status_code == 401

def test_expired_and_forged_sessions_rejected(client):
    api, _, factory = client
    with factory() as db:
        for session in db.scalars(select(LoginSession)):
            session.expires_at = now()-timedelta(seconds=1)
        db.commit()
    assert api.get('/api/auth/me').status_code == 401
    api.headers['Authorization']='Bearer invented-token'
    assert api.get('/api/documents').status_code == 401
