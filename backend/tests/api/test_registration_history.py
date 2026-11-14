import pytest
from sqlalchemy import select
from app.models.auth import Account
from app.operations.models import Event
from tests.api.test_registration_review import register,login

pytestmark=pytest.mark.parametrize('client',[False],indirect=True)

def test_history_keeps_each_decision_and_snapshot_after_reapplication(client):
    api,_,factory=client;admin=api.headers['Authorization']
    person=register(api,'nursing').json();path=f"/api/account-reviews/{person['id']}/decision"
    rejection={'version':1,'action':'reject','note':'请补充任职证明'}
    assert api.post(path,json=rejection).status_code==200
    assert api.post(path,json=rejection).status_code==200
    login(api)
    assert api.put('/api/auth/application',json={'version':2,'requested_role':'kitchen','application_note':'改为食堂入职'}).status_code==200
    api.headers['Authorization']=admin
    assert api.post(path,json={'version':3,'action':'approve','role':'user','note':'核实后安排护工岗位'}).status_code==200
    with factory() as db:
        db.get(Account,person['id']).name='后来更名'
        db.commit()
    data=api.get('/api/account-reviews/history').json()
    assert data['total']==2
    records={row['result']:row for row in data['items']}
    assert records['reject']['requested_role']=='nursing'
    assert records['reject']['granted_role'] is None
    assert records['reject']['application_note']=='入职核对'
    assert records['reject']['application_version']==1
    assert records['approve']['requested_role']=='kitchen'
    assert records['approve']['granted_role']=='user'
    assert records['approve']['application_note']=='改为食堂入职'
    assert records['approve']['application_version']==3
    for row in records.values():
        assert row['applicant_name']=='新员工'
        assert row['reviewer_name']=='测试用户'
        assert row['phone_hint']=='139****0001'
        assert row['reviewed_at']
        assert '13977770001' not in str(row) and 'password' not in str(row)
    assert api.put(f"/api/account-reviews/{person['id']}/status",json={'version':4,'status':'disabled','note':'离职'}).status_code==200
    assert api.get('/api/account-reviews/history').json()['total']==2
    filtered=api.get('/api/account-reviews/history?result=reject&page_size=1').json()
    assert filtered['total']==1 and filtered['items'][0]['note']=='请补充任职证明'
    assert len(api.get('/api/account-reviews/history?page_size=1').json()['items'])==1
    assert api.get('/api/account-reviews/history?page_size=1&page=3').json()['items']==[]


def test_history_old_events_and_access_control(client):
    api,_,factory=client;admin=api.headers['Authorization'];person=register(api).json()
    with factory() as db:
        director=db.scalar(select(Account).where(Account.role=='admin'))
        db.add(Event(id='old-event',actor_id=director.id,action='account_application_approve',object_id=person['id'],data={'requested_role':'user','granted_role':'user','note':'历史通过'}));db.commit()
    row=api.get('/api/account-reviews/history').json()['items'][0]
    assert row['applicant_name']=='新员工' and row['application_version'] is None
    assert row['application_note'] is None
    assert api.get('/api/account-reviews/history?result=disabled').status_code==422
    assert api.get('/api/account-reviews/history?page=0').status_code==422
    assert api.get('/api/account-reviews/history?page_size=101').status_code==422
    assert api.post(f"/api/account-reviews/{person['id']}/decision",json={'version':1,'action':'approve','role':'user'}).status_code==200
    login(api)
    assert api.get('/api/account-reviews/history').status_code==403
    api.headers.pop('Authorization')
    assert api.get('/api/account-reviews/history').status_code==401
