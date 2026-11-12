from sqlalchemy import select,func
from app.models.auth import Account,LoginSession
from app.models.resident import Resident,ResidentAssignment,ResidentChange
from app.models import KnowledgeBase
from scripts.reset_accounts import reset
from tests.api.test_residents import staff,payload


def test_reset_preserves_residents_and_knowledge_and_releases_phones(client):
    api,_,factory=client
    sid,_=staff(api)
    resident=api.post('/api/residents',json=payload(assigned_account_ids=[sid])).json()
    with factory() as db:
        change=db.scalar(select(ResidentChange))
        change.after={**change.after,'bound_account':{'id':sid,'name':'护理员','phone_hint':'139****0001'},'resident':{'id':resident['id'],'name':'测试老人'}}
        db.commit()
        result=reset(db)
        assert result['accounts']==2
        assert db.scalar(select(func.count()).select_from(Account).where(Account.status=='active'))==2
        assert db.scalar(select(func.count()).select_from(ResidentAssignment))==1
        result=reset(db,True)
        assert result['accounts']==2 and result['assignments']==1
        assert db.scalar(select(func.count()).select_from(Account).where(Account.status!='archived'))==0
        assert db.scalar(select(func.count()).select_from(LoginSession))==0
        assert db.scalar(select(func.count()).select_from(ResidentAssignment))==0
        assert db.get(Resident,resident['id']).name=='测试老人'
        assert db.get(KnowledgeBase,'medication') is not None
        change=db.scalar(select(ResidentChange))
        assert change.after['bound_account']['name']=='历史匿名操作人'
        assert change.after['bound_account']['phone_hint']=='已清理'
        assert change.after['resident']['name']=='测试老人'
        assert all(row.actor_name=='历史操作人（账号已清理）' for row in db.scalars(select(ResidentChange)))
        assert all(not row.phone.isdigit() for row in db.scalars(select(Account)))
        assert reset(db,True)['accounts']==0
    assert api.get('/api/auth/me').status_code==401
    result=api.post('/api/auth/register',json={'phone':'13800000000','name':'重新开始','password':'Again1234','requested_role':'user'})
    assert result.status_code==201 and result.json()['status']=='pending'

from tests.operations.test_workflow import ops,submit,med,approve
from app.operations.models import Draft,Execution,Shift,Credential
from datetime import datetime,timedelta

def test_reset_cancels_pending_work_and_keeps_historical_foreign_keys(ops):
    api,factory,tokens,ids,resident,validator=ops
    medication=submit(api,'medication',med(resident)).json()
    api.headers['Authorization']=tokens['admin'];assert approve(api,medication).status_code==200
    api.headers['Authorization']=tokens['nursing']
    start=datetime.now()+timedelta(days=2)
    schedule=submit(api,'schedule',{'shifts':[{'account_id':ids['user'],'start_at':start.isoformat(),'end_at':(start+timedelta(hours=2)).isoformat(),'hourly_rate':'20'}]}).json()
    api.headers['Authorization']=tokens['admin'];assert approve(api,schedule).status_code==200
    api.headers['Authorization']=tokens['user']
    pending=submit(api,'incident',{'resident_id':resident['id'],'severity':'routine','observation':'历史观察'}).json()
    with factory() as db:
        result=reset(db,True)
        assert result['cancelled_drafts']==1 and result['cancelled_executions']==1
        assert db.get(Draft,pending['id']).status=='rejected'
        assert db.scalar(select(Execution)).status=='cancelled'
        shift=db.scalar(select(Shift))
        assert db.get(Account,shift.account_id).status=='archived'
        assert db.scalar(select(func.count()).select_from(Credential))==0
        assert db.get(Resident,resident['id']) is not None
