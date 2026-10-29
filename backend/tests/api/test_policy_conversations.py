from uuid import uuid4
import pytest
from sqlalchemy import select, func
from app.core.exceptions import BusinessError
from app.models import KnowledgeDocument
from app.models.conversation import PolicyConversation, PolicyTurn
from app.schemas.chat import PolicyAnswer, Citation, WebSource, AnswerChecks
from app.services import conversations
from test_policy_graph import hit

BASE='/api/agents/policy/conversations'


@pytest.fixture()
def chat(client,monkeypatch):
    api,storage,factory=client
    calls=[]
    def generate(question,*args,**kwargs):
        calls.append(question)
        return PolicyAnswer(status='answered',answer='依据原文回答。【1】【2】',citations=[Citation(index=1,hit=hit()),
            Citation(index=2,source_type='web',web=WebSource(title='官方资料',url='https://hangzhou.gov.cn/policy',content='当次网页正文',retrieved_at='2026-10-29T00:00:00Z'))],
            retrieved_hits=[hit()],web_sources=[WebSource(title='官方资料',url='https://hangzhou.gov.cn/policy',content='当次网页正文',retrieved_at='2026-10-29T00:00:00Z')],
            web_status='success',model='test-qwen',knowledge_scope=['general'],steps=['verify_grounding'],answer_checks=AnswerChecks(status='passed',checked_paragraphs=1,accepted_paragraphs=1))
    monkeypatch.setattr('app.api.v1.chat.run_policy',generate)
    return api,factory,calls


def create(api):
    response=api.post(BASE)
    assert response.status_code==201,response.text
    return response.json()['id']


def send(api,key,question='政策问题',request_id=None,retry=False):
    return api.post(f'{BASE}/{key}/turns',json={'request_id':request_id or str(uuid4()),'question':question,'retry':retry})


def test_persist_replay_dedupe_and_deleted_source_snapshot(chat,monkeypatch):
    api,factory,calls=chat
    with factory() as db:
        db.add(KnowledgeDocument(id='policy',kb_id='general',name='政策说明',type='TXT',status='vectorized',content='已上传原文'))
        db.commit()
    key=create(api);request_id=str(uuid4())
    response=send(api,key,'原文如何解释',request_id)
    assert response.status_code==200,response.text
    turn=response.json();assert turn['status']=='succeeded' and turn['response']['answer_checks']['status']=='passed'
    assert len(calls)==1
    again=send(api,key,'原文如何解释',request_id)
    assert again.json()==turn and len(calls)==1
    assert send(api,key,'其他问题',request_id).status_code==409
    with factory() as db:
        db.delete(db.get(KnowledgeDocument,'policy'));db.commit()
    monkeypatch.setattr('app.api.v1.chat.run_policy',lambda *a,**kw:pytest.fail('replay must not invoke models'))
    replay=api.get(f'{BASE}/{key}').json()
    assert replay['turns'][0]['response']==turn['response']
    assert replay['turns'][0]['response']['web_sources'][0]['content']=='当次网页正文'
    assert replay['conversation']['title']=='原文如何解释'
    assert api.get(BASE).json()['items'][0]['id']==key
    assert api.delete(f'{BASE}/{key}').status_code==204
    assert api.get(f'{BASE}/{key}').status_code==404
    with factory() as db: assert db.scalar(select(func.count()).select_from(PolicyTurn))==0


def test_server_history_ignores_client_supplied_history_and_is_bounded(chat):
    api,factory,calls=chat;key=create(api)
    for i in range(5): assert send(api,key,f'第{i}问').status_code==200
    history=calls[-1].history
    assert len(history)==6 and history[0].content=='第1问'
    assert history[-1].role=='assistant'
    response=api.post(f'{BASE}/{key}/turns',json={'request_id':str(uuid4()),'question':'篡改历史','history':[]})
    assert response.status_code==422
    page=api.get(f'{BASE}/{key}?page_size=2').json()
    assert [t['seq'] for t in page['turns']]==[4,5] and page['has_more']
    older=api.get(f"{BASE}/{key}?page_size=2&before_seq={page['next_before_seq']}").json()
    assert [t['seq'] for t in older['turns']]==[2,3]


def test_failed_turn_is_saved_retry_is_explicit_and_failed_history_is_skipped(chat,monkeypatch):
    api,factory,calls=chat;key=create(api);request_id=str(uuid4())
    original=__import__('app.api.v1.chat',fromlist=['run_policy']).run_policy
    failures=[]
    def fail(*a,**kw): failures.append(True);raise BusinessError('测试模型暂不可用。',502)
    monkeypatch.setattr('app.api.v1.chat.run_policy',fail)
    assert send(api,key,'失败问题',request_id).status_code==502
    failed=api.get(f'{BASE}/{key}').json()['turns'][0]
    assert failed['status']=='failed' and failed['response'] is None and failed['attempts']==1
    assert send(api,key,'失败问题',request_id).json()['status']=='failed'
    assert len(failures)==1
    monkeypatch.setattr('app.api.v1.chat.run_policy',original)
    retry=send(api,key,'失败问题',request_id,retry=True)
    assert retry.status_code==200 and retry.json()['attempts']==2
    assert calls[-1].history==[]
    assert send(api,key,'后续问题').status_code==200 and len(calls[-1].history)==2


def test_active_generation_lock_blocks_ask_and_delete_but_allows_read(chat):
    api,factory,calls=chat;key=create(api)
    root=api.app.dependency_overrides[conversations.get_conversation_lock_dir]()
    with conversations.conversation_lock(root,key):
        assert send(api,key).status_code==409
        assert api.delete(f'{BASE}/{key}').status_code==409
        assert api.get(f'{BASE}/{key}').status_code==200
    assert not calls


def test_interrupted_request_recovered_only_when_no_writer_holds_lock(chat):
    api,factory,calls=chat;key=create(api);request_id=str(uuid4())
    with factory() as db:
        db.add(PolicyTurn(id=request_id,conversation_id=key,seq=1,question='中断问题',status='running',attempts=1));db.commit()
    root=api.app.dependency_overrides[conversations.get_conversation_lock_dir]()
    with conversations.conversation_lock(root,key):
        assert api.get(f'{BASE}/{key}').json()['turns'][0]['status']=='running'
    recovered=api.get(f'{BASE}/{key}').json()['turns'][0]
    assert recovered['status']=='failed' and '中断' in recovered['error']
    assert send(api,key,'中断问题',request_id,retry=True).json()['status']=='succeeded'


def test_request_cannot_be_reused_across_conversations(chat):
    api,factory,calls=chat;a=create(api);b=create(api);request_id=str(uuid4())
    assert send(api,a,'问题',request_id).status_code==200
    assert send(api,b,'问题',request_id).status_code==409
    assert len(calls)==1


def test_old_failed_turn_cannot_be_retried_after_a_later_turn(chat,monkeypatch):
    api,factory,calls=chat;key=create(api);request_id=str(uuid4())
    import app.api.v1.chat as endpoint
    original=endpoint.run_policy
    monkeypatch.setattr(endpoint,'run_policy',lambda *a,**kw:(_ for _ in ()).throw(BusinessError('模型不可用',502)))
    assert send(api,key,'失败问题',request_id).status_code==502
    monkeypatch.setattr(endpoint,'run_policy',original)
    assert send(api,key,'后来的问题').status_code==200
    assert calls[-1].history==[]
    assert send(api,key,'失败问题',request_id,retry=True).status_code==409
    assert len(calls)==1


def test_internal_error_is_not_persisted_with_sensitive_exception_details(chat,monkeypatch):
    api,factory,calls=chat;key=create(api);request_id=str(uuid4())
    def fail(*a,**kw): raise RuntimeError('test-sensitive-internal-message')
    monkeypatch.setattr('app.api.v1.chat.run_policy',fail)
    with pytest.raises(RuntimeError): send(api,key,'问题',request_id)
    replay=api.get(f'{BASE}/{key}').json()['turns'][0]
    assert replay['status']=='failed' and replay['response'] is None
    assert 'test-sensitive' not in replay['error']
