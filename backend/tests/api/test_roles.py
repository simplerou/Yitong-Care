import pytest
from uuid import uuid4
from sqlalchemy import select
from app.models.auth import Account
from app.models.conversation import PolicyConversation
from scripts.setup_admin import provision


def regular_user(api, phone):
    assert api.post('/api/auth/register',json={'phone':phone,'name':'普通用户','password':'Regular123','role':'admin'}).status_code==201
    result=api.post('/api/auth/login',json={'phone':phone,'password':'Regular123'}).json()
    api.headers['Authorization']='Bearer '+result['token']
    assert result['user']['role']=='user'
    return result['user']['id']


def test_user_cannot_manage_knowledge(client):
    api,_,_=client
    regular_user(api,'13900000001')
    for method,path in [('GET','/api/documents'),('POST','/api/documents'),('GET','/api/knowledge-bases'),('GET','/api/retrieval/logs')]:
        assert api.request(method,path).status_code==403
    assert api.get('/api/agents/policy/config').status_code==200


@pytest.mark.parametrize('agent',['policy','health','medication','diet','safety','mind'])
def test_conversations_are_private_across_accounts(client, agent):
    api,_,_=client
    base='/api/agents/'+agent+'/conversations'
    admin_token=api.headers['Authorization']
    created=api.post(base,json={})
    assert created.status_code==201,created.text
    legacy_id=created.json()['id']
    regular_user(api,'13900000002')
    assert api.get(base).json()['items']==[]
    assert api.get(base+'/'+legacy_id).status_code==404
    assert api.delete(base+'/'+legacy_id).status_code==404
    own=api.post(base,json={})
    assert own.status_code==201,own.text
    assert len(api.get(base).json()['items'])==1
    own_id=own.json()['id']
    api.headers['Authorization']=admin_token
    assert api.get(base+'/'+own_id).status_code==404
    assert [r['id'] for r in api.get(base).json()['items']]==[legacy_id]


def test_explicit_legacy_claim_preserves_other_owners(client):
    api,_,factory=client
    with factory() as db:
        admin=db.scalar(select(Account).where(Account.phone=='13800000000'))
        old=PolicyConversation(id=str(uuid4()),title='旧测试数据')
        other=PolicyConversation(id=str(uuid4()),title='其他账号',owner_id='other')
        db.add_all([old,other]);db.commit()
        counts=provision(db,admin.phone,admin.name,claim_legacy=True)
        assert counts['policy_conversation']==1
        db.refresh(old);db.refresh(other)
        assert old.owner_id==admin.id
        assert other.owner_id=='other'
        assert provision(db,admin.phone,admin.name,claim_legacy=True)['policy_conversation']==0
