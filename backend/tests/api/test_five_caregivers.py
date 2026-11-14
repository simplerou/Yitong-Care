import pytest
from sqlalchemy import select,func
from app.models.auth import Account
from app.models.resident import Resident,ResidentAssignment,ResidentChange
from app.operations.models import Event
from scripts.seed_residents import read_dataset,import_dataset
from scripts.setup_caregivers import FIVE_ACCOUNTS,provision_five_by_four


def test_five_caregivers_each_see_four_and_repeat_preserves_passwords(client):
    api,_,factory=client
    with factory() as db:
        import_dataset(db,read_dataset())
        preview=provision_five_by_four(db)
        assert len(preview['created'])==5
        assert db.scalar(select(func.count()).select_from(Account))==1
        assert db.scalar(select(func.count()).select_from(ResidentAssignment))==0
        result=provision_five_by_four(db,apply=True)
        assert len(result['created'])==5 and result['assigned']==20
        assert [item['count'] for item in result['counts']]==[4]*5
        assert db.scalar(select(func.count()).select_from(ResidentAssignment))==20
        assert db.scalar(select(func.count()).select_from(Event).where(Event.action=='account_application_approve'))==5
        hashes={row.id:row.password_hash for row in db.scalars(select(Account))}
        again=provision_five_by_four(db,apply=True)
        assert again['created']==[] and again['assigned']==0
        assert {row.id:row.password_hash for row in db.scalars(select(Account))}==hashes
        assert db.scalar(select(func.count()).select_from(ResidentChange))==40
    for item in result['created']:
        response=api.post('/api/auth/login',json={'phone':item['phone'],'password':item['password']})
        assert response.status_code==200
        assert response.json()['user']['role']=='user' and response.json()['user']['status']=='active'
        api.headers['Authorization']='Bearer '+response.json()['token']
        assert api.get('/api/residents').json()['total']==4
        assert api.get('/api/account-reviews/history').status_code==403


def test_five_mode_refuses_missing_residents_and_does_not_create_accounts(client):
    _,_,factory=client
    with factory() as db:
        with pytest.raises(ValueError,match='20位在院老人'):
            provision_five_by_four(db,apply=True)
        assert db.scalar(select(func.count()).select_from(Account))==1


def test_five_mode_rolls_back_conflicting_phone(client):
    api,_,factory=client
    phone=FIVE_ACCOUNTS[-1][0]
    api.post('/api/auth/register',json={'phone':phone,'name':'另一个申请人','password':'Other12345'})
    with factory() as db:
        import_dataset(db,read_dataset())
        with pytest.raises(ValueError,match='占用'):
            provision_five_by_four(db,apply=True)
        assert db.scalar(select(func.count()).select_from(Account))==2
        assert db.scalar(select(func.count()).select_from(ResidentAssignment))==0


def test_reset_five_passwords_revokes_changed_sessions_and_preserves_assignments(client):
    from app.core.auth import hash_password,verify_password
    from scripts.setup_caregivers import reset_five_passwords,FIVE_INITIAL_PASSWORD
    api,_,factory=client
    with factory() as db:
        import_dataset(db,read_dataset())
        result=provision_five_by_four(db,apply=True)
        assert all(item['password']==FIVE_INITIAL_PASSWORD for item in result['created'])
        first=db.scalar(select(Account).where(Account.phone==FIVE_ACCOUNTS[0][0]))
        first.password_hash=hash_password('Old123456');db.commit()
    login=api.post('/api/auth/login',json={'phone':FIVE_ACCOUNTS[0][0],'password':'Old123456'}).json()
    api.headers['Authorization']='Bearer '+login['token']
    with factory() as db:
        assert reset_five_passwords(db)==1
        assert verify_password('Old123456',db.get(Account,first.id).password_hash)
        assert reset_five_passwords(db,apply=True)==1
        assert reset_five_passwords(db,apply=True)==0
        assert db.scalar(select(func.count()).select_from(ResidentAssignment))==20
    assert api.get('/api/auth/me').status_code==401
    for phone,_ in FIVE_ACCOUNTS:
        assert api.post('/api/auth/login',json={'phone':phone,'password':'hg123456'}).status_code==200
