import logging

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import BusinessError
from app.models import DocumentChunk, EmbeddingTask, KnowledgeDocument
from app.schemas.embedding import EmbeddingRequest, EmbeddingTaskRead
from app.services.document_service import find_document
from app.services.embedding.base import Embedder
from app.services.vectorstore.index_manager import IndexManager
from app.services.vectorstore.locking import index_write_lock

logger = logging.getLogger(__name__)
ACTIVE = ['queued', 'running']


def task_read(task: EmbeddingTask) -> EmbeddingTaskRead:
    return EmbeddingTaskRead(id=task.id, doc_id=task.doc_id, model=task.model, model_name=task.model_name,
        dimensions=task.dim, batch_size=task.batch_size, status=task.status, phase=task.phase, progress=task.progress,
        total=task.total, processed=task.processed, log=task.log, error_message=task.error_message, index_version=task.index_version)


def require_no_active_task(db: Session):
    if db.scalar(select(EmbeddingTask.id).where(EmbeddingTask.status.in_(ACTIVE)).limit(1)):
        raise BusinessError('已有向量任务在执行，请等待完成；若服务曾中断，请在任务页面点击重试。', 409)


def create_task(db: Session, doc_id: str, request: EmbeddingRequest, embedder: Embedder, manager: IndexManager) -> EmbeddingTaskRead:
    if request.model is not None and request.model != embedder.key:
        raise BusinessError('所选模型与当前后端配置不一致，请刷新页面。', 409)
    with index_write_lock(manager.root):
        require_no_active_task(db)
        doc = find_document(db, doc_id, lock=True)
        if doc.status not in {'chunked', 'vectorized'}:
            raise BusinessError('请先保存文档切块，再执行向量入库。', 409)
        ids = list(db.scalars(select(DocumentChunk.id).where(DocumentChunk.doc_id == doc_id).order_by(DocumentChunk.seq)))
        if not ids:
            raise BusinessError('该文档没有已保存的文本块。', 409)
        task = EmbeddingTask(doc_id=doc_id, model=embedder.key, model_name=embedder.model, dim=embedder.dimensions,
            batch_size=request.batch_size, total=len(ids), processed=0, progress=0, phase='reading', status='queued',
            chunk_ids=ids, log=[f'任务已创建：共 {len(ids)} 段，批次 {request.batch_size}。'])
        # 新任务重新生成；失败任务的 retry 才复用已完成的批次。
        db.execute(update(DocumentChunk).where(DocumentChunk.doc_id == doc_id).values(
            embedding=None, embedding_model=None, embedding_dim=None, vector_status='pending'))
        doc.status = 'vectorizing'
        db.add(task); db.commit()
        return task_read(task)


def retry_task(db: Session, task_id: int, embedder: Embedder, manager: IndexManager) -> EmbeddingTaskRead:
    with index_write_lock(manager.root):
        task = db.get(EmbeddingTask, task_id)
        if task is None:
            raise BusinessError('任务不存在。', 404)
        if task.status == 'succeeded':
            raise BusinessError('任务已完成，重新向量化请创建新任务。', 409)
        latest = db.scalar(select(EmbeddingTask.id).where(EmbeddingTask.doc_id == task.doc_id).order_by(EmbeddingTask.id.desc()).limit(1))
        if latest != task.id:
            raise BusinessError('已有更新的任务，请创建新的向量任务。', 409)
        if task.model != embedder.key:
            task.status = 'failed'
            task.error_message = '模型配置已变化，旧任务已停止，请新建向量任务。'
            doc = find_document(db, task.doc_id, lock=True)
            doc.status = 'chunked'
            db.commit()
            raise BusinessError(task.error_message, 409)
        if db.scalar(select(EmbeddingTask.id).where(EmbeddingTask.id != task.id, EmbeddingTask.status.in_(ACTIVE)).limit(1)):
            raise BusinessError('另有向量任务正在执行，请稍后重试。', 409)
        ids = list(db.scalars(select(DocumentChunk.id).where(DocumentChunk.doc_id == task.doc_id).order_by(DocumentChunk.seq)))
        if ids != task.chunk_ids:
            raise BusinessError('文档已重新切块，请创建新的向量任务。', 409)
        doc = find_document(db, task.doc_id, lock=True)
        task.status = 'queued'; task.phase = 'reading'; task.error_message = None
        task.log = [*task.log, '任务重试：将继续处理尚未完成的批次。']
        doc.status = 'vectorizing'; db.commit()
        return task_read(task)


def run_task(task_id: int, factory: sessionmaker, embedder: Embedder, manager: IndexManager):
    # 全局单写者保证跨进程不会并发发布索引；模型调用期间不占用数据库会话。
    with index_write_lock(manager.root, blocking=True):
        try:
            with factory() as db:
                task = db.get(EmbeddingTask, task_id)
                if task is None or task.status != 'queued':
                    return
                if task.model != embedder.key:
                    raise BusinessError('模型配置已经变化，请新建任务。', 409)
                rows = db.scalars(select(DocumentChunk).where(DocumentChunk.doc_id == task.doc_id).order_by(DocumentChunk.seq)).all()
                if [r.id for r in rows] != task.chunk_ids:
                    raise BusinessError('文档切块已变化，请新建任务。', 409)
                pending = [(r.id, r.content) for r in rows if not (r.embedding is not None and r.embedding_model == task.model and r.embedding_dim == task.dim and r.vector_status == 'ready')]
                processed = len(rows) - len(pending)
                batch_size, doc_id, total = task.batch_size, task.doc_id, task.total
                task.status = 'running'; task.phase = 'embedding'; task.processed = processed
                task.log = [*task.log, f'调用 {task.model_name}，输出 {task.dim} 维；已完成 {processed}/{total} 段。']
                db.commit()
            for start in range(0, len(pending), batch_size):
                batch = pending[start:start + batch_size]
                vectors = np.asarray(embedder.embed([text for _id, text in batch]), dtype=np.float32)
                if vectors.shape != (len(batch), embedder.dimensions) or not np.isfinite(vectors).all():
                    raise BusinessError('Embedding 输出向量维度或数值异常。', 502)
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                if not np.isfinite(norms).all() or (norms <= 0).any():
                    raise BusinessError('Embedding 返回了无效向量。', 502)
                vectors = vectors / norms
                with factory() as db:
                    task = db.get(EmbeddingTask, task_id)
                    for (chunk_id, _text), vector in zip(batch, vectors):
                        chunk = db.get(DocumentChunk, chunk_id)
                        if chunk is None:
                            raise BusinessError('文本块已变化，任务停止。', 409)
                        chunk.embedding = np.asarray(vector, dtype='<f4').tobytes()
                        chunk.embedding_model = embedder.key; chunk.embedding_dim = embedder.dimensions; chunk.vector_status = 'ready'
                    processed += len(batch)
                    task.processed = processed; task.progress = min(92, round(processed / total * 92))
                    task.log = [*task.log, f'批次 {start // batch_size + 1}：完成 {processed}/{total} 段。']
                    db.commit()
            with factory() as db:
                task = db.get(EmbeddingTask, task_id)
                task.phase = 'indexing'; task.progress = 95
                task.log = [*task.log, '向量已保存到数据库，正在发布 FAISS 索引。']
                db.commit()
            with factory() as db:
                task = db.get(EmbeddingTask, task_id)
                doc = find_document(db, doc_id, lock=True)
                doc.status = 'vectorized'
                record = manager.rebuild(db, doc.kb_id, embedder.key, embedder.dimensions)
                task.status = 'succeeded'; task.phase = 'done'; task.progress = 100; task.index_version = record.version
                task.log = [*task.log, f'索引版本 v{record.version} 发布完成，共 {record.vector_count} 条向量。']
                db.commit()
        except Exception as exc:
            message = exc.message if isinstance(exc, BusinessError) else '向量任务失败，请检查模型连接、数据库或索引目录后重试。'
            logger.warning('Embedding task %s failed: %s', task_id, type(exc).__name__)
            with factory() as db:
                task = db.get(EmbeddingTask, task_id)
                if task and task.status != 'succeeded':
                    task.status = 'failed'; task.error_message = message
                    task.log = [*task.log, message]
                    doc = db.get(KnowledgeDocument, task.doc_id)
                    if doc: doc.status = 'chunked'
                    db.commit()
