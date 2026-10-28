from collections import defaultdict
from time import perf_counter, time_ns
from uuid import uuid4

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.models import DocumentChunk, KnowledgeDocument, RetrievalHit, RetrievalLog
from app.schemas.retrieval import RetrievalRecord, SearchHit, SearchRequest, SearchResult
from app.services.retrieval.bm25 import bm25, rrf
from app.services.embedding.base import Embedder
from app.services.vectorstore.index_manager import IndexManager


def eligible(model: str):
    return [DocumentChunk.vector_status == 'ready', DocumentChunk.embedding_model == model,
            DocumentChunk.embedding.is_not(None), KnowledgeDocument.status == 'vectorized']



def search(db: Session, request: SearchRequest, embedder: Embedder, manager: IndexManager, allowed_kb_ids: list[str] | None = None) -> SearchResult:
    started = perf_counter()
    if request.scope != 'all' and db.get(KnowledgeDocument, request.scope) is None:
        raise BusinessError('所选文档已不存在，请重新选择知识范围。', 404)
    conditions = [*eligible(embedder.key), DocumentChunk.embedding_dim == embedder.dimensions]
    if request.scope != 'all': conditions.append(DocumentChunk.doc_id == request.scope)
    if allowed_kb_ids is not None: conditions.append(DocumentChunk.kb_id.in_(allowed_kb_ids))
    pool = db.execute(select(DocumentChunk.id, DocumentChunk.kb_id, DocumentChunk.content).join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.doc_id).where(*conditions)).all()
    groups = defaultdict(set)
    for chunk_id, kb_id, _ in pool: groups[kb_id].add(chunk_id)
    hits = []
    if pool:
        query = np.asarray(embedder.embed([request.query])[0], dtype=np.float32)
        if query.shape != (embedder.dimensions,) or not np.isfinite(query).all() or np.linalg.norm(query) <= 0:
            raise BusinessError('问题向量无效，请检查 Embedding 服务。', 502)
        query /= np.linalg.norm(query)
        semantic = {}
        for kb_id, allowed_ids in groups.items():
            record = manager.latest(db, kb_id, embedder.key)
            if record is None:
                raise BusinessError('数据库中有向量但索引尚未发布，请先重建索引。', 503)
            index = manager.load(record)
            import faiss
            if not allowed_ids.issubset(set(faiss.vector_to_array(index.id_map).tolist())):
                raise BusinessError('向量索引与数据库不一致，请先重建索引。', 503)
            semantic.update(manager.search(record, query, allowed_ids, max(60, request.top_k * 4)))
        budget = max(60, request.top_k * 4)
        semantic = dict(sorted(((key, score) for key, score in semantic.items() if score >= request.threshold),
                               key=lambda item: (-item[1], item[0]))[:budget])
        lexical = bm25(request.query, [(key, text) for key, _, text in pool], limit=budget)
        fused = rrf(semantic, lexical)
        semantic_ranks = {key: rank for rank, key in enumerate(semantic, 1)}
        lexical_ranks = {key: rank for rank, key in enumerate(lexical, 1)}
        ids = set(semantic) | set(lexical)
        if ids:
            rows = db.execute(select(DocumentChunk, KnowledgeDocument).join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.doc_id)
                .where(DocumentChunk.id.in_(ids), *conditions)).all()
            for chunk, doc in rows:
                cosine = semantic.get(chunk.id)
                if cosine is None:
                    vector = np.frombuffer(chunk.embedding, dtype='<f4')
                    if vector.shape != query.shape or not np.isfinite(vector).all():
                        raise BusinessError('数据库向量异常，请重新入库。', 503)
                    norm = np.linalg.norm(vector)
                    cosine = float(np.dot(query, vector / norm)) if norm > 0 else 0
                cosine = max(-1., min(1., cosine))
                lex = lexical.get(chunk.id, 0.)
                score = fused[chunk.id]
                hits.append(SearchHit(chunk_id=chunk.id, doc_id=doc.id, kb_id=doc.kb_id, doc_name=doc.name,
                    type=doc.type, source=doc.source or '本地上传', seq=chunk.seq, start=chunk.start_offset,
                    end=chunk.start_offset + chunk.chars, chars=chunk.chars, text=chunk.content,
                    score=score, cos=round(cosine, 6), lexical_score=round(lex, 6), bm25_score=round(lex, 6),
                    semantic_rank=semantic_ranks.get(chunk.id), bm25_rank=lexical_ranks.get(chunk.id)))
            hits.sort(key=lambda h: (-h.score, h.chunk_id)); hits = hits[:request.top_k]
    took = max(1, round((perf_counter() - started) * 1000))
    record = RetrievalLog(id=f'{time_ns():020d}_{uuid4().hex[:12]}', query=request.query, scope=request.scope, top_k=request.top_k,
        strategy='bm25_rrf', threshold=request.threshold, took_ms=took, hit_count=len(hits), vector_count=len(pool), model=embedder.key)
    db.add(record); db.flush()
    for rank, hit in enumerate(hits, 1):
        db.add(RetrievalHit(log_id=record.id, chunk_id=hit.chunk_id, rank=rank, score=hit.score, snapshot=hit.model_dump()))
    db.commit()
    return SearchResult(log_id=record.id, query=request.query, scope=request.scope, top_k=request.top_k,
        strategy='bm25_rrf', threshold=request.threshold, took_ms=took, vector_count=len(pool), model=embedder.model, hits=hits)


def replay(db: Session, log_id: str) -> SearchResult:
    record = db.get(RetrievalLog, log_id)
    if record is None: raise BusinessError('检索记录不存在或已删除。', 404)
    snapshots = db.scalars(select(RetrievalHit).where(RetrievalHit.log_id == log_id).order_by(RetrievalHit.rank)).all()
    return SearchResult(log_id=record.id, query=record.query, scope=record.scope, top_k=record.top_k,
        strategy=record.strategy, threshold=record.threshold, took_ms=record.took_ms, vector_count=record.vector_count,
        model=record.model, hits=[SearchHit.model_validate(row.snapshot) for row in snapshots], historical=True)


def logs(db: Session, page: int, page_size: int):
    total = db.scalar(select(func.count()).select_from(RetrievalLog)) or 0
    rows = db.scalars(select(RetrievalLog).order_by(RetrievalLog.created_at.desc(), RetrievalLog.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    records = []
    for row in rows:
        first = db.scalar(select(RetrievalHit).where(RetrievalHit.log_id == row.id, RetrievalHit.rank == 1))
        records.append(RetrievalRecord(id=row.id, query=row.query, scope=row.scope, top_k=row.top_k,
            strategy=row.strategy, threshold=row.threshold, took_ms=row.took_ms, hit_count=row.hit_count,
            top_score=first.score if first else None, top_source=first.snapshot['doc_name'] if first else None, created_at=row.created_at))
    return {'items': records, 'total': total, 'page': page, 'page_size': page_size}


def remove_log(db: Session, log_id: str | None = None):
    if log_id:
        row = db.get(RetrievalLog, log_id)
        if row is None: raise BusinessError('检索记录不存在。', 404)
        db.delete(row)
    else:
        db.execute(delete(RetrievalLog))
    db.commit()
