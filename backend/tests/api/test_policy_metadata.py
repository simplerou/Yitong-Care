from datetime import date
from uuid import uuid4
from sqlalchemy import select
from app.models import KnowledgeDocument
from app.models.conversation import PolicyTurn
from app.services import conversations


def test_policy_metadata_roundtrip_validation_and_unknown_defaults(client):
    api,_,factory=client
    with factory() as db:
        db.add(KnowledgeDocument(id='policy',kb_id='general',name='政策',type='TXT',status='parsed',content='原文'));db.commit()
    assert api.get('/api/documents/policy').json()['policy_metadata'] is None
    invalid=api.put('/api/documents/policy/policy',json={'validity':'effective'})
    assert invalid.status_code==422
    fields={'document_number':'测试〔2026〕1号','regions':['杭州市'],'validity':'repealed','verified_on':date.today().isoformat(),'verification_source':'主管部门公告','replaces':['测试〔2025〕1号']}
    response=api.put('/api/documents/policy/policy',json=fields)
    assert response.status_code==200,response.text
    saved=api.get('/api/documents/policy').json()['policy_metadata']
    assert saved['regions']==['杭州市'] and saved['validity']=='repealed'
    assert api.put('/api/documents/missing/policy',json={}).status_code==404


def test_context_persistence_progress_read_and_writer_lock(client,monkeypatch):
    api,_,factory=client
    base='/api/agents/policy/conversations'
    key=api.post(base).json()['id']
    response=api.put(f'{base}/{key}/context',json={'region':'杭州市','age':90,'benefit':'养老服务补贴'})
    assert response.status_code==200 and response.json()['context']['age']==90
    assert api.get(f'{base}/{key}').json()['conversation']['context']['region']=='杭州市'
    root=api.app.dependency_overrides[conversations.get_conversation_lock_dir]()
    with conversations.conversation_lock(root,key):
        assert api.put(f'{base}/{key}/context',json={}).status_code==409
    request_id=str(uuid4())
    assert api.get(f'{base}/{key}/turns/{request_id}/progress').status_code==404
    with factory() as db:
        db.add(PolicyTurn(id=request_id,conversation_id=key,seq=1,question='问题',status='running',stage='retrieve',attempts=1));db.commit()
    assert api.get(f'{base}/{key}/turns/{request_id}/progress').json()['stage']=='retrieve'
    other=api.post(base).json()['id']
    assert api.get(f'{base}/{other}/turns/{request_id}/progress').status_code==404
    assert api.put(f'{base}/{key}/context',json={'age':200}).status_code==422
    assert api.put(f'{base}/{key}/context',json={}).json()['context']['region']==''
