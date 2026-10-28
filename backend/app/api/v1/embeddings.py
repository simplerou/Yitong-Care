from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.deps import DatabaseSession, get_session_factory
from app.core.exceptions import BusinessError
from app.models import DocumentChunk, EmbeddingTask, KnowledgeBase, KnowledgeDocument
from app.schemas.embedding import EmbeddingRequest, EmbeddingTaskRead
from app.services.embedding.openai_compatible import OpenAICompatibleEmbedder, get_embedder
from app.services.embedding_service import create_task, require_no_active_task, retry_task, run_task, task_read
from app.services.vectorstore.index_manager import IndexManager, get_index_manager
from app.services.vectorstore.locking import index_write_lock

router = APIRouter(tags=['vectors'])
Model = Annotated[OpenAICompatibleEmbedder, Depends(get_embedder)]
Manager = Annotated[IndexManager, Depends(get_index_manager)]
Factory = Annotated[sessionmaker, Depends(get_session_factory)]


@router.get('/embeddings/models')
def models(embedder: Model):
    try:
        embedder.ensure_configured()
        configured, hint = True, ''
    except BusinessError as exc:
        configured, hint = False, exc.message
    return {'models':[{'id':embedder.key, 'name':embedder.model, 'dimensions':embedder.dimensions,
                       'configured':configured, 'hint':hint}], 'batch_sizes':[8,16,32]}


@router.post('/documents/{doc_id}/embeddings', response_model=EmbeddingTaskRead, status_code=202)
def enqueue(doc_id: str, request: EmbeddingRequest, background: BackgroundTasks, db: DatabaseSession, embedder: Model, manager: Manager, factory: Factory):
    embedder.ensure_configured()
    task = create_task(db, doc_id, request, embedder, manager)
    background.add_task(run_task, task.id, factory, embedder, manager)
    return task


@router.get('/embeddings/tasks', response_model=list[EmbeddingTaskRead])
def tasks(db: DatabaseSession, doc_id: str | None = Query(default=None, max_length=64)):
    statement = select(EmbeddingTask)
    if doc_id: statement = statement.where(EmbeddingTask.doc_id == doc_id)
    return [task_read(task) for task in db.scalars(statement.order_by(EmbeddingTask.id.desc()).limit(20))]


@router.get('/embeddings/tasks/{task_id}', response_model=EmbeddingTaskRead)
def task(task_id: int, db: DatabaseSession):
    result = db.get(EmbeddingTask, task_id)
    if result is None: raise BusinessError('向量任务不存在。',404)
    return task_read(result)


@router.post('/embeddings/tasks/{task_id}/retry', response_model=EmbeddingTaskRead, status_code=202)
def retry(task_id: int, background: BackgroundTasks, db: DatabaseSession, embedder: Model, manager: Manager, factory: Factory):
    embedder.ensure_configured()
    task = retry_task(db, task_id, embedder, manager)
    background.add_task(run_task, task.id, factory, embedder, manager)
    return task


@router.get('/vector-index/status')
def status(db: DatabaseSession, embedder: Model, manager: Manager):
    rows = db.execute(select(DocumentChunk.kb_id, func.count(DocumentChunk.id), func.count(func.distinct(DocumentChunk.doc_id))).join(
        KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.doc_id).where(
        DocumentChunk.embedding_model == embedder.key, DocumentChunk.embedding_dim == embedder.dimensions,
        DocumentChunk.vector_status == 'ready', DocumentChunk.embedding.is_not(None), KnowledgeDocument.status == 'vectorized',
    ).group_by(DocumentChunk.kb_id)).all()
    by_kb = {kb_id:(count, documents) for kb_id,count,documents in rows}
    indexes = []
    for kb in db.scalars(select(KnowledgeBase)):
        record = manager.latest(db,kb.id,embedder.key)
        count,documents = by_kb.get(kb.id,(0,0))
        healthy, message = count == 0 and record is None, ''
        if record:
            try:
                loaded = manager.load(record)
                import faiss
                actual_ids = set(faiss.vector_to_array(loaded.id_map).tolist())
                expected_ids = set(db.scalars(select(DocumentChunk.id).join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.doc_id).where(
                    DocumentChunk.kb_id == kb.id, DocumentChunk.embedding_model == embedder.key, DocumentChunk.embedding_dim == embedder.dimensions,
                    DocumentChunk.vector_status == 'ready', KnowledgeDocument.status == 'vectorized', DocumentChunk.embedding.is_not(None))))
                healthy = actual_ids == expected_ids
                if not healthy: message = '索引与数据库数量或 ID 不一致，可从数据库重建。'
            except BusinessError as exc:
                healthy, message = False, exc.message
        elif count:
            message = '索引缺失，请从数据库重建。'
        indexes.append({'kb_id':kb.id,'kb_name':kb.name,'version':record.version if record else 0,
                        'vectors':count,'indexed_vectors':record.vector_count if record else 0,'documents':documents,
                        'healthy':healthy,'status':record.status if record else 'empty','message':message})
    return {'model':embedder.model,'model_id':embedder.key,'dimensions':embedder.dimensions,'index_type':'FAISS FlatIP + IDMap2',
            'vectors':sum(r['vectors'] for r in indexes),'documents':sum(r['documents'] for r in indexes),
            'healthy':all(r['healthy'] for r in indexes),'indexes':indexes}


class RebuildRequest(BaseModel):
    kb_id: str | None = None


@router.post('/vector-index/rebuild')
def rebuild(request: RebuildRequest, db: DatabaseSession, embedder: Model, manager: Manager):
    if not embedder.model: raise BusinessError('请先填写 Embedding 模型配置。',503)
    with index_write_lock(manager.root):
        require_no_active_task(db)
        ids = list(db.scalars(select(KnowledgeBase.id).where(KnowledgeBase.id == request.kb_id))) if request.kb_id else list(db.scalars(select(KnowledgeBase.id)))
        if request.kb_id and not ids: raise BusinessError('知识库不存在。',404)
        versions = []
        for kb_id in ids:
            record = manager.rebuild(db,kb_id,embedder.key,embedder.dimensions)
            versions.append({'kb_id':kb_id,'version':record.version,'vectors':record.vector_count})
        db.commit()
    return {'rebuilt':versions}
