from sqlalchemy import select,func
from app.models.auth import Account
from app.models.resident import ResidentAssignment,ResidentChange
from scripts.setup_caregivers import provision
from tests.api.test_residents import staff,payload


def test_provision_is_atomic_balanced_and_repeatable(client):
    api,_,factory=client
    sid,_=staff(api)
    for i in range(8):
        data=payload(name=f'老人{i}',assigned_account_ids=[sid] if i==0 else [])
        assert api.post('/api/residents',json=data).status_code==201
    with factory() as db:
        preview=provision(db)
        assert len(preview['created'])==3 and preview['assigned']==7
        assert db.scalar(select(func.count()).select_from(Account).where(Account.role=='user'))==1
        result=provision(db,True)
        assert len(result['created'])==3
        assert all(row['count']==2 for row in result['counts'])
        assert db.scalar(select(func.count()).select_from(ResidentAssignment))==8
        assert db.scalar(select(func.count()).select_from(ResidentChange).where(ResidentChange.reason.like('初始化护工%')))==7
        again=provision(db,True)
        assert again['created']==[] and again['assigned']==0
