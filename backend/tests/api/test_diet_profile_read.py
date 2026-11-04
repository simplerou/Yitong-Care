from sqlalchemy import select,func
from app.models.meals import MealProfile
from app.services.chat.llm import get_llm
class Reader:
    model='fake'
    def complete_json(self,system,payload,**kwargs):
        assert set(payload)=={'allergies','dietary_notes','chronic_conditions'}
        assert '私密姓名' not in str(payload)
        return {'facts':[dict(field='allergens',value='鸡蛋',source='allergies',quote='鸡蛋过敏')],'questions':[]}
def test_read_without_save(client):
    api,_,factory=client
    row=api.post('/api/residents',json={'name':'私密姓名','source':'入住资料','allergies':'鸡蛋过敏'}).json()
    api.app.dependency_overrides[get_llm]=lambda:Reader()
    response=api.post('/api/meals/profiles/'+row['id']+'/read')
    assert response.status_code==200,response.text
    assert response.json()['suggestion']['confirmed'] is False
    assert response.json()['resident_id']==row['id']
    with factory() as db:assert db.scalar(select(func.count()).select_from(MealProfile))==0
def test_missing_resident(client):
    api,_,_=client
    assert api.post('/api/meals/profiles/00000000-0000-0000-0000-000000000001/read').status_code==404

def test_non_admin_cannot_read(client):
    from app.models.auth import Account
    api,_,factory=client
    with factory() as db:
        db.scalar(select(Account).where(Account.phone=='13800000000')).role='user'
        db.commit()
    assert api.post('/api/meals/profiles/00000000-0000-0000-0000-000000000001/read').status_code==403
