import hmac
from fastapi import FastAPI,Depends,Header,HTTPException
from app.operations.contracts import CheckRequest,current_date
from validation_service.config import ValidationSettings
from validation_service.graph import get_graph,GraphUnavailable
from validation_service.rules import evaluate

app=FastAPI(title='禾龄通独立规则校验服务',version='1.0.0')
def settings():return ValidationSettings()
def authorized(authorization:str=Header(default=''),cfg=Depends(settings)):
    token=cfg.validation_service_token.get_secret_value()
    if not token or not hmac.compare_digest(authorization,'Bearer '+token):raise HTTPException(401,'校验服务身份无效')
    return cfg

def facts(cfg):
    try:
        from validation_service.manifest import Manifest
        data=get_graph(cfg).facts();paths=data.pop('graph_paths',None)
        validated=Manifest.model_validate(data).model_dump(mode='json')
        if validated['demo'] and not cfg.validation_allow_demo:raise GraphUnavailable()
        if paths is not None:validated['graph_paths']=paths
        return validated
    except (GraphUnavailable,ValueError,KeyError):raise HTTPException(503,'图事实层不可用，禁止生成草稿') from None

@app.get('/health')
def health():return {'status':'up','service':'validation'}
@app.post('/check')
def check(request:CheckRequest,cfg=Depends(authorized)):
    try:return evaluate(request,facts(cfg))
    except (KeyError,ValueError,TypeError,ArithmeticError):raise HTTPException(503,'规则事实不完整，禁止生成草稿') from None
@app.get('/catalog')
def catalog(cfg=Depends(authorized)):
    data=facts(cfg)
    return {'version':data['version'],'demo':data.get('demo',False),'allergens':sorted({a for f in list(data['foods'].values())+list(data['drugs'].values()) for a in f.get('allergens',[])}),'diseases':data['diseases'],'foods':list(data['foods'].values()),'drugs':[{'id':d['id'],'name':d['name']} for d in data['drugs'].values()]}
@app.get('/evidence/{drug_id}')
def evidence(drug_id:str,category:str='insert',on_date:str|None=None,cfg=Depends(authorized)):
    from datetime import date
    from validation_service.rules import valid_evidence
    item=facts(cfg)['drugs'].get(drug_id)
    if category!='insert' or not item or not valid_evidence(item.get('evidence',{})) or (on_date and on_date!=current_date().isoformat()):raise HTTPException(404,'没有当前有效说明书证据')
    return {'drug_id':drug_id,'category':category,**item['evidence']}
