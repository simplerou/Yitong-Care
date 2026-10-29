from pathlib import Path
import numpy as np
import pytest
from sqlalchemy import select

from app.core.exceptions import BusinessError
from app.models import DocumentChunk, EmbeddingTask, KnowledgeDocument, VectorIndex
from app.services.embedding.openai_compatible import get_embedder
from app.services.vectorstore.index_manager import IndexManager, get_index_manager


class FakeEmbedder:
    model = 'test-only-semantic-model'
    dimensions = 3
    key = 'test-only-model@3:1'
    def __init__(self):
        self.calls = []
        self.fail_on = None
    def ensure_configured(self): pass
    def embed(self,texts):
        self.calls.append(list(texts))
        if len(self.calls) == self.fail_on:
            raise BusinessError('测试：模型暂不可用。',502)
        result=[]
        for text in texts:
            result.append([1.,0.,0.] if any(w in text for w in ['助餐','食堂']) else [0.,1.,0.] if any(w in text for w in ['跌倒','扶手']) else [0.,0.,1.])
        return np.asarray(result,dtype=np.float32)


@pytest.fixture()
def vectors(client,tmp_path):
    api,storage,factory=client
    storage.max_bytes=1024*1024
    embedder=FakeEmbedder();manager=IndexManager(tmp_path/'faiss')
    api.app.dependency_overrides[get_embedder]=lambda:embedder
    api.app.dependency_overrides[get_index_manager]=lambda:manager
    yield api,embedder,manager,factory


def document(api,text,name='资料.txt'):
    uploaded=api.post('/api/documents',files={'file':(name,text.encode())})
    assert uploaded.status_code==202,uploaded.text
    doc_id=uploaded.json()['id']
    saved=api.post(f'/api/documents/{doc_id}/chunks',json={'size':100,'overlap':20})
    assert saved.status_code==200,saved.text
    return doc_id


def embed(api,doc_id,batch=8):
    response=api.post(f'/api/documents/{doc_id}/embeddings',json={'batch_size':batch})
    assert response.status_code==202,response.text
    job=api.get(f"/api/embeddings/tasks/{response.json()['id']}").json()
    return job


def test_real_faiss_search_scope_and_persistent_history(vectors):
    api,model,manager,factory=vectors
    dining=document(api,'社区助餐可以到食堂窗口登记。' * 12,'助餐资料.txt')
    safety=document(api,'预防跌倒应安装扶手和防滑设施。' * 12,'安全资料.txt')
    first=embed(api,dining);second=embed(api,safety)
    assert first['status']=='succeeded' and second['status']=='succeeded'
    assert first['index_version']==1 and second['index_version']==2
    status=api.get('/api/vector-index/status').json()
    assert status['healthy'] and status['documents']==2 and status['vectors']>0
    result=api.post('/api/retrieval/search',json={'query':'助餐','top_k':3,'threshold':.12})
    assert result.status_code==200,result.text
    data=result.json();assert data['hits'] and all(h['doc_id']==dining for h in data['hits'])
    assert all(0 < h['score'] <= 2/61 and h['text'] and h['end']-h['start']==h['chars'] for h in data['hits'])
    assert data['strategy']=='bm25_rrf'
    assert all(h['bm25_score'] > 0 and h['semantic_rank'] and h['bm25_rank'] for h in data['hits'])
    scoped=api.post('/api/retrieval/search',json={'query':'助餐','scope':safety,'threshold':.12}).json()
    assert scoped['hits']==[]
    logs=api.get('/api/retrieval/logs').json()
    assert logs['total']==2
    replay=api.get('/api/retrieval/logs/'+data['log_id']).json()
    assert replay['historical'] and replay['hits']==data['hits']
    assert api.delete('/api/documents/'+dining).status_code==204
    replay=api.get('/api/retrieval/logs/'+data['log_id']).json()
    assert replay['hits']==data['hits']
    current=api.post('/api/retrieval/search',json={'query':'助餐','threshold':.12}).json()
    assert current['hits']==[]
    assert api.delete('/api/retrieval/logs').status_code==204
    assert api.get('/api/retrieval/logs').json()['total']==0
    assert api.get('/api/retrieval/logs/'+data['log_id']).status_code==404


def test_missing_and_corrupt_index_can_rebuild_without_model_calls(vectors):
    api,model,manager,factory=vectors
    doc_id=document(api,'社区助餐登记服务。'*25)
    assert embed(api,doc_id)['status']=='succeeded'
    with factory() as db: path=manager.path(manager.latest(db,'general',model.key).path)
    calls=len(model.calls)
    path.unlink()
    assert not api.get('/api/vector-index/status').json()['healthy']
    assert api.post('/api/retrieval/search',json={'query':'助餐'}).status_code==503
    before=len(model.calls)
    assert api.post('/api/vector-index/rebuild',json={}).status_code==200
    assert len(model.calls)==before
    assert api.get('/api/vector-index/status').json()['healthy']
    with factory() as db: new_path=manager.path(manager.latest(db,'general',model.key).path)
    new_path.write_bytes(b'corrupt index')
    assert not api.get('/api/vector-index/status').json()['healthy']
    assert api.post('/api/vector-index/rebuild',json={}).status_code==200
    assert api.post('/api/retrieval/search',json={'query':'助餐'}).json()['hits']


def test_failed_batch_retry_resumes_and_rechunk_invalidates(vectors):
    api,model,manager,factory=vectors
    doc_id=document(api,'社区助餐服务可以到食堂咨询登记。'*100)
    model.fail_on=2
    task=embed(api,doc_id)
    assert task['status']=='failed' and task['processed']==8
    assert api.get('/api/documents/'+doc_id).json()['status']=='chunked'
    assert api.get('/api/documents').json()['stats']['vectors']==0
    task_id=task['id'];model.fail_on=None
    response=api.post(f'/api/embeddings/tasks/{task_id}/retry')
    assert response.status_code==202,response.text
    task=api.get(f'/api/embeddings/tasks/{task_id}').json()
    assert task['status']=='succeeded' and task['processed']==task['total']
    # 第一批只调用一次；重试不会再发送已经成功的 8 段。
    assert sum(len(batch) for batch in model.calls)==task['total']+8
    assert api.post('/api/documents/'+doc_id+'/chunks',json={'size':150,'overlap':0}).status_code==200
    assert api.post('/api/retrieval/search',json={'query':'助餐'}).json()['hits']==[]
    with factory() as db:
        assert all(c.embedding is None for c in db.scalars(select(DocumentChunk).where(DocumentChunk.doc_id==doc_id)))


def test_interrupted_job_recovery_and_model_separation(vectors):
    api,model,manager,factory=vectors
    doc_id=document(api,'社区助餐服务。'*20)
    task=embed(api,doc_id)
    with factory() as db:
        row=db.get(EmbeddingTask,task['id']);row.status='running'
        db.get(KnowledgeDocument,doc_id).status='vectorizing';db.commit()
    assert api.post(f"/api/embeddings/tasks/{task['id']}/retry").status_code==202
    assert api.get(f"/api/embeddings/tasks/{task['id']}").json()['status']=='succeeded'
    model.key='different-model@3:2'
    assert api.post('/api/retrieval/search',json={'query':'助餐'}).json()['hits']==[]
    invalid=api.post(f'/api/documents/{doc_id}/embeddings',json={'model':'wrong-model'})
    assert invalid.status_code==409


def test_index_publication_rollback_keeps_previous_version(vectors):
    api,model,manager,factory=vectors
    doc_id=document(api,'社区助餐服务。'*20)
    assert embed(api,doc_id)['status']=='succeeded'
    with factory() as db:
        original=manager.latest(db,'general',model.key)
        original_path=manager.path(original.path);original_bytes=original_path.read_bytes()
        newer=manager.rebuild(db,'general',model.key,model.dimensions)
        assert newer.version==2
        db.rollback()
    with factory() as db:
        assert manager.latest(db,'general',model.key).version==1
        assert original_path.read_bytes()==original_bytes
        assert manager.load(manager.latest(db,'general',model.key)).ntotal>0


def test_writer_lock_blocks_mutations_and_old_model_job_can_exit(vectors):
    from app.services.vectorstore.locking import index_write_lock
    api,model,manager,factory=vectors
    doc_id=document(api,'社区助餐服务。'*20)
    with index_write_lock(manager.root):
        assert api.post(f'/api/documents/{doc_id}/chunks',json={'size':150,'overlap':0}).status_code==409
        assert api.delete('/api/documents/'+doc_id).status_code==409
        assert api.post(f'/api/documents/{doc_id}/embeddings',json={}).status_code==409
    task=embed(api,doc_id)
    with factory() as db:
        db.get(EmbeddingTask,task['id']).status='running'
        db.get(KnowledgeDocument,doc_id).status='vectorizing';db.commit()
    model.key='new-model@3:2'
    assert api.post(f"/api/embeddings/tasks/{task['id']}/retry").status_code==409
    assert api.get(f"/api/embeddings/tasks/{task['id']}").json()['status']=='failed'
    assert embed(api,doc_id)['status']=='succeeded'


def test_bm25_can_recall_below_semantic_threshold(vectors):
    api, model, manager, factory = vectors
    target = document(api, '护理保险登记政策。')
    other = document(api, '助餐食堂服务。')
    embed(api, target); embed(api, other)
    # Fake model gives query [1,0,0], target [0,0,1]. BM25 still recalls shared terms.
    data = api.post('/api/retrieval/search', json={'query':'助餐 护理保险', 'scope':target, 'threshold':.6}).json()
    assert data['strategy'] == 'bm25_rrf'
    assert data['hits'] and all(hit['doc_id'] == target for hit in data['hits'])
    hit = data['hits'][0]
    assert hit['cos'] == 0 and hit['semantic_rank'] is None and hit['bm25_rank'] == 1
    assert hit['score'] == pytest.approx(1/61)
    from app.services.retrieval.hybrid import search
    from app.schemas.retrieval import SearchRequest
    with factory() as db:
        assert search(db, SearchRequest(query='护理保险'), model, manager, allowed_kb_ids=[]).hits == []


def test_legacy_history_keeps_original_scores(vectors):
    from app.models import RetrievalLog, RetrievalHit
    api, model, manager, factory = vectors
    target = document(api, '助餐登记。')
    embed(api, target)
    data = api.post('/api/retrieval/search', json={'query':'助餐'}).json()
    with factory() as db:
        log = db.get(RetrievalLog, data['log_id'])
        log.strategy = 'legacy_weighted'
        row = db.scalar(select(RetrievalHit).where(RetrievalHit.log_id == log.id))
        snapshot = dict(row.snapshot)
        for field in ('bm25_score', 'bm25_rank', 'semantic_rank'): snapshot.pop(field)
        snapshot['score'] = .78; snapshot['lexical_score'] = .5
        row.score = .78; row.snapshot = snapshot
        db.commit()
    before = len(model.calls)
    replay = api.get('/api/retrieval/logs/' + data['log_id']).json()
    assert replay['strategy'] == 'legacy_weighted'
    assert replay['hits'][0]['score'] == .78
    assert replay['hits'][0]['bm25_score'] is None
    assert len(model.calls) == before


def test_policy_api_uses_real_retrieval_and_scoped_citations(vectors):
    from app.services.chat.llm import get_llm
    from test_policy_graph import Model, decision
    api, model, manager, factory = vectors
    doc = document(api, '杭州市社区助餐可向食堂申请登记。')
    embed(api, doc)
    llm = Model(decision(), {'sufficient':True,'paragraphs':[{'text':'社区助餐可向食堂申请登记。','sources':[1]}]})
    api.app.dependency_overrides[get_llm] = lambda:llm
    response = api.post('/api/agents/policy/chat', json={'question':'杭州市社区助餐如何登记'})
    assert response.status_code == 200, response.text
    result=response.json()
    assert result['status']=='answered' and result['citations'][0]['hit']['doc_id']==doc
    assert result['retrieval_log_id']
    assert api.get('/api/retrieval/logs/'+result['retrieval_log_id']).status_code==200
    assert api.post('/api/agents/policy/chat',json={'question':'   '}).status_code==422
    assert api.post('/api/agents/policy/chat',json={'question':'test','history':[{'role':'system','content':'hack'}]}).status_code==422
