from tests.api.test_residents import staff,payload
from tests.api.test_meals import clock,profile,save,publish,WEEK


def test_caregiver_meals_scope_choice_edit_kitchen_and_revocation(client):
    api,_,_=client
    admin=api.headers['Authorization']
    sid,token=staff(api)
    _,other=staff(api,'13912340002')
    resident=api.post('/api/residents',json=payload(assigned_account_ids=[sid])).json()
    key=resident['id'];url=f'/api/meals/residents/{key}'
    assert profile(api,key).status_code==200
    menu=save(api)
    assert publish(api,menu).status_code==200
    api.headers['Authorization']=token
    result=api.get(url,params={'week_start':WEEK})
    assert result.status_code==200,result.text
    slots=result.json()['slots'];assert len(slots)==21
    data={'menu_id':menu['id'],'day':0,'meal':'breakfast','option_id':slots[0]['options'][0]['id'],'version':0}
    assert api.put(url,json=data).status_code==200
    assert api.put(url,json=data).status_code==409
    assert api.put(url,json={**data,'option_id':slots[0]['options'][1]['id'],'version':1}).status_code==200
    assert api.get(url,params={'week_start':WEEK}).json()['slots'][0]['selection']['version']==2
    api.headers['Authorization']=other
    assert api.get(url,params={'week_start':WEEK}).status_code==404
    assert api.put(url,json=data).status_code==404
    api.headers['Authorization']=admin
    kitchen=api.get(f"/api/meals/menus/{menu['id']}/kitchen",params={'meal_date':WEEK,'meal':'breakfast'}).json()
    assert sum(row['count'] for row in kitchen['options'])==1
    assert api.put(f'/api/residents/{key}/assignments',json={'version':1,'account_ids':[],'reason':'交班'}).status_code==200
    api.headers['Authorization']=token
    assert api.get(url,params={'week_start':WEEK}).status_code==404
    assert api.put(url,json={**data,'version':2}).status_code==404


def test_unreviewed_profile_can_view_but_not_choose(client):
    api,_,_=client
    sid,token=staff(api)
    row=api.post('/api/residents',json=payload(assigned_account_ids=[sid])).json()
    menu=save(api)
    assert publish(api,menu,ack=True).status_code==200
    api.headers['Authorization']=token
    url=f"/api/meals/residents/{row['id']}"
    response=api.get(url,params={'week_start':WEEK}).json()
    assert response['reviewed'] is False
    assert response['slots'][0]['options'][0]['reasons']
    assert api.put(url,json={'menu_id':menu['id'],'day':0,'meal':'breakfast','option_id':menu['slots'][0]['options'][0]['id']}).status_code==409
