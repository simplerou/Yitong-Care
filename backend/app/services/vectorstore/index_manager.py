from collections import OrderedDict
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from threading import RLock
from uuid import uuid4
import os
import re

import faiss
import numpy as np
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.models import DocumentChunk, KnowledgeDocument, VectorIndex


class IndexManager:
    """MySQL 为唯一数据源；索引文件不可变，数据库提交后读侧按版本热加载。"""
    def __init__(self, root: Path):
        self.root = root.resolve()
        self._cache = OrderedDict()
        self._cache_lock = RLock()

    def path(self, name: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]+-[a-f0-9]+-v[0-9]+-[a-f0-9]+\.faiss", name):
            raise BusinessError("索引路径无效，请从数据库重建索引。", 503)
        return self.root / name

    def rebuild(self, db: Session, kb_id: str, model: str, dim: int) -> VectorIndex:
        # 调用方须持有 index_write_lock；允许事务内刚变为 vectorized 的文档参与构建。
        db.flush()
        count = db.scalar(select(func.count(DocumentChunk.id)).join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.doc_id).where(
            DocumentChunk.kb_id == kb_id, DocumentChunk.embedding_model == model, DocumentChunk.embedding_dim == dim,
            DocumentChunk.vector_status == 'ready', KnowledgeDocument.status == 'vectorized')) or 0
        if count > 200_000:
            raise BusinessError('该知识库超过 20 万条向量，请先评估 HNSW 或独立向量服务。', 409)
        rows = db.execute(select(DocumentChunk.id, DocumentChunk.embedding).join(
            KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.doc_id,
        ).where(
            DocumentChunk.kb_id == kb_id, DocumentChunk.embedding_model == model,
            DocumentChunk.embedding_dim == dim, DocumentChunk.vector_status == 'ready',
            KnowledgeDocument.status == 'vectorized',
        ).order_by(DocumentChunk.id)).all()
        vectors = []
        ids = []
        for chunk_id, data in rows:
            if data is None or len(data) != dim * 4:
                raise BusinessError('数据库中的向量长度异常，请重新向量化对应文档。', 409)
            vector = np.frombuffer(data, dtype='<f4').copy()
            norm = np.linalg.norm(vector)
            if not np.isfinite(vector).all() or not np.isfinite(norm) or norm <= 0:
                raise BusinessError('数据库中存在无效向量，请重新向量化对应文档。', 409)
            vectors.append(vector / norm); ids.append(chunk_id)
        index = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))
        if ids:
            index.add_with_ids(np.ascontiguousarray(vectors, dtype=np.float32), np.asarray(ids, dtype=np.int64))
        version = (db.scalar(select(func.max(VectorIndex.version)).where(VectorIndex.kb_id == kb_id, VectorIndex.model == model)) or 0) + 1
        filename = f'{sha256(kb_id.encode()).hexdigest()[:12]}-{sha256(model.encode()).hexdigest()[:12]}-v{version}-{uuid4().hex}.faiss'
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.path(filename)
        temporary = destination.with_suffix('.part')
        try:
            faiss.write_index(index, str(temporary))
            with temporary.open('rb') as stream:
                os.fsync(stream.fileno())
            digest = sha256(temporary.read_bytes()).hexdigest()
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        db.execute(update(VectorIndex).where(
            VectorIndex.kb_id == kb_id, VectorIndex.model == model,
            VectorIndex.status.in_(['ready', 'stale']),
        ).values(status='superseded'))
        record = VectorIndex(kb_id=kb_id, model=model, dim=dim, metric='cosine', vector_count=len(ids), version=version,
                             path=filename, status='ready', sha256=digest, built_at=datetime.now(UTC).replace(tzinfo=None))
        db.add(record)
        db.flush()
        return record

    def latest(self, db: Session, kb_id: str, model: str) -> VectorIndex | None:
        return db.scalar(select(VectorIndex).where(VectorIndex.kb_id == kb_id, VectorIndex.model == model,
            VectorIndex.status.in_(['ready', 'stale'])).order_by(VectorIndex.version.desc()).limit(1))

    def load(self, record: VectorIndex):
        path = self.path(record.path)
        try:
            stat = path.stat()
            signature = (record.path, stat.st_mtime_ns, stat.st_size, record.sha256)
            with self._cache_lock:
                if signature in self._cache:
                    self._cache.move_to_end(signature)
                    return self._cache[signature]
                if not record.sha256 or sha256(path.read_bytes()).hexdigest() != record.sha256:
                    raise ValueError('checksum mismatch')
                index = faiss.read_index(str(path))
                if not isinstance(index, faiss.IndexIDMap2) or index.d != record.dim or index.ntotal != record.vector_count:
                    raise ValueError('index metadata mismatch')
                if len(set(faiss.vector_to_array(index.id_map).tolist())) != index.ntotal:
                    raise ValueError('duplicate IDs')
                self._cache[signature] = index
                while len(self._cache) > 4:
                    self._cache.popitem(last=False)
                return index
        except (OSError, ValueError, RuntimeError) as exc:
            raise BusinessError('向量索引缺失或损坏，请点击“从数据库重建索引”。', 503) from exc

    def search(self, record: VectorIndex, query: np.ndarray, allowed_ids: set[int], limit: int) -> dict[int, float]:
        index = self.load(record)
        if not index.ntotal or not allowed_ids:
            return {}
        # 逐步扩大候选，保证指定文档范围不会被其他文档挤掉。
        count = min(index.ntotal, max(32, limit * 4))
        while True:
            scores, ids = index.search(np.ascontiguousarray(query.reshape(1, -1), dtype=np.float32), count)
            result = {int(i): float(s) for i, s in zip(ids[0], scores[0]) if int(i) in allowed_ids}
            if len(result) >= limit or count == index.ntotal:
                return dict(list(result.items())[:limit])
            count = min(index.ntotal, count * 2)


@lru_cache
def manager_for(root: str) -> IndexManager:
    return IndexManager(Path(root))


def get_index_manager() -> IndexManager:
    return manager_for(str(get_settings().faiss_index_dir))
