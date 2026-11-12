from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from validation_service.main import app,settings
from validation_service.config import ValidationSettings
from validation_service.graph import DEMO
from validation_service.rules import evaluate
from app.operations.contracts import CheckRequest
P={'allergens':[],'diseases':[],'medicines':[],'energy_min':'80','energy_max':'200','protein_min':'2','sodium_max':'500','source':'演示'}
def check(**kwargs):return CheckRequest.model_validate({'kind':'medication','patients':[P],'medicines':[{'drug_id':'DEMO-A','mg_per_dose':'1','times_daily':1}],**kwargs})
def test_numeric_and_multihop_rules_are_deterministic():
    out=evaluate(check(medicines=[{'drug_id':'DEMO-A','mg_per_dose':'11','times_daily':2}]),DEMO)
    assert not out['passed'] and out['issues'][0]['code']=='dose_limit'
    out=evaluate(check(kind='meal_swap',foods=[{'food_id':'DEMO-GRAPE','grams':'200'}]),DEMO)
    assert any(i['code']=='food_drug_conflict' for i in out['issues'])
    assert out['paths'][0]['nodes']==['DEMO-A','demo-active-a','demo-grape','DEMO-GRAPE']
    assert out['paths'][0]['evidence']['location']
    out=evaluate(check(medicines=[{'drug_id':'DEMO-A','mg_per_dose':'1','times_daily':1},{'drug_id':'DEMO-B','mg_per_dose':'1','times_daily':1}]),DEMO)
    assert any(i['code']=='polypharmacy' for i in out['issues'])
@pytest.mark.parametrize('foods,patient,code',[
 ([{'food_id':'DEMO-FISH','grams':'100'}],{**P,'allergens':['demo-fish-allergen']},'allergen_conflict'),
 ([{'food_id':'DEMO-RICE','grams':'1'}],P,'energy_target'),
 ([{'food_id':'MISSING','grams':'100'}],P,'unknown_food'),
 ([{'food_id':'DEMO-RICE','grams':'100'}],{**P,'diseases':['unknown']},'unknown_disease')])
def test_food_dose_and_unknown_data_cannot_silently_pass(foods,patient,code):
    out=evaluate(check(kind='menu',patients=[patient],medicines=[],foods=foods),DEMO)
    assert not out['passed'] and any(i['code']==code for i in out['issues'])
def test_missing_expired_evidence_and_duplicate_dose():
    facts=deepcopy(DEMO);facts['drugs']['DEMO-A']['evidence']['valid_to']='2020-01-01'
    assert not evaluate(check(),facts)['passed']
    with pytest.raises(ValidationError):check(medicines=[{'drug_id':'DEMO-A','mg_per_dose':'1','times_daily':1}]*2)
def test_independent_http_service_auth_and_graph_failure():
    cfg=ValidationSettings(_env_file=None,validation_service_token='local-test',validation_graph_mode='fixture',validation_allow_demo=True)
    app.dependency_overrides[settings]=lambda:cfg
    try:
        with TestClient(app) as api:
            assert api.post('/check',json=check().model_dump(mode='json')).status_code==401
            api.headers['Authorization']='Bearer local-test'
            assert api.post('/check',json=check().model_dump(mode='json')).json()['passed']
            assert api.get('/evidence/DEMO-A').json()['section']=='1.1'
            cfg.validation_allow_demo=False
            assert api.post('/check',json=check().model_dump(mode='json')).status_code==503
    finally:app.dependency_overrides.clear()

def test_graph_hash_is_order_independent_and_duplicate_active_is_blocked():
    a=deepcopy(DEMO);b=deepcopy(DEMO);b['conflicts'].reverse()
    assert evaluate(check(),a)['graph_hash']==evaluate(check(),b)['graph_hash']
    a['drugs']['DEMO-C']={**a['drugs']['DEMO-A'],'id':'DEMO-C','name':'虚构重复成分药品'}
    out=evaluate(check(medicines=[{'drug_id':'DEMO-A','mg_per_dose':'1','times_daily':1},{'drug_id':'DEMO-C','mg_per_dose':'1','times_daily':1}]),a)
    assert not out['passed'] and any(i['code']=='duplicate_active_ingredient' for i in out['issues'])

def test_http_client_rejects_malformed_pass_flag():
    import httpx
    from fastapi import HTTPException
    from app.operations.validator import ValidationClient
    cfg=ValidationSettings(_env_file=None,validation_service_token='test-token')
    payload=evaluate(check(),DEMO)
    transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload))
    client=ValidationClient(cfg,transport)
    assert client.check(check().model_dump(mode='json'))['passed'] is True
    payload['passed']='true'
    with pytest.raises(HTTPException) as error:client.check(check().model_dump(mode='json'))
    assert error.value.status_code==503
