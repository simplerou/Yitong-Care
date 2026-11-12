from tests.api.test_residents import staff,payload
from tests.api.test_meals import clock,profile,save,publish,WEEK

def test_caregiver_meals_are_read_only_but_admin_can_arrange(client):
    api,_,_=client;admin=api.headers['Authorization'];sid,token=staff(api)
    row=api.post('/api/residents',json=payload(assigned_account_ids=[sid])).json();key=row['id'];url=f'/api/meals/residents/{key}'
    assert profile(api,key).status_code==200
    menu=save(api);assert publish(api,menu).status_code==200
    api.headers['Authorization']=token
    response=api.get(url,params={'week_start':WEEK}).json();assert len(response['slots'])==21 and response['caregiver_readonly']
    data={'menu_id':menu['id'],'day':0,'meal':'breakfast','option_id':menu['slots'][0]['options'][0]['id']}
    assert api.put(url,json=data).status_code==403
    api.headers['Authorization']=admin;assert api.put(url,json=data).status_code==200
    api.headers['Authorization']=token;assert api.get(url,params={'week_start':WEEK}).json()['slots'][0]['selection'] is not None
    api.headers['Authorization']=admin
    assert api.put('/api/residents/'+key+'/assignments',json={'version':1,'account_ids':[],'reason':'交班'}).status_code==200
    api.headers['Authorization']=token;assert api.get(url,params={'week_start':WEEK}).status_code==404

def test_unreviewed_profile_cannot_be_modified_by_caregiver(client):
    api,_,_=client;sid,token=staff(api)
    row=api.post('/api/residents',json=payload(assigned_account_ids=[sid])).json();menu=save(api);assert publish(api,menu,ack=True).status_code==200
    api.headers['Authorization']=token
    url=f"/api/meals/residents/{row['id']}"
    assert api.get(url,params={'week_start':WEEK}).json()['reviewed'] is False
    assert api.put(url,json={'menu_id':menu['id'],'day':0,'meal':'breakfast','option_id':menu['slots'][0]['options'][0]['id']}).status_code==403
