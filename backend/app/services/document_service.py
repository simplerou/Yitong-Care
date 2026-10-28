import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import BusinessError
from app.models import DocumentChunk, KnowledgeBase, KnowledgeDocument, VectorIndex
from app.schemas.chunk import ChunkParameters, ChunkRead, ChunkResult
from app.schemas.document import DocumentDetail, DocumentPage, DocumentSummary, KnowledgeStats
from app.services.chunking.splitter import split_text
from app.services.parser import parse_file
from app.services.parser.text import ParseError
from app.services.storage import LocalFileStorage

logger = logging.getLogger(__name__)
ALLOWED_TYPES = {"pdf", "docx", "txt", "md", "markdown"}


def validate_filename(filename: str | None) -> tuple[str, str]:
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or len(name) > 512:
        raise BusinessError("文件名不能为空且不能超过 512 个字符。", 422)
    suffix = Path(name).suffix.lstrip(".").lower()
    if suffix not in ALLOWED_TYPES:
        raise BusinessError("仅支持 PDF、DOCX、TXT 和 Markdown；旧版 DOC 请另存为 DOCX。", 415)
    return name, suffix


def find_document(db: Session, document_id: str, *, lock: bool = False) -> KnowledgeDocument:
    statement = select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
    if lock:
        statement = statement.with_for_update()
    doc = db.scalar(statement)
    if doc is None:
        raise BusinessError("文档不存在或已被删除。", 404)
    return doc


def chunk_read(chunk: DocumentChunk, previous_end: int = 0) -> ChunkRead:
    return ChunkRead(
        id=chunk.id, doc_id=chunk.doc_id, seq=chunk.seq, content=chunk.content,
        start_offset=chunk.start_offset, chars=chunk.chars,
        vector_status=chunk.vector_status,
        overlap_chars=max(0, previous_end - chunk.start_offset),
    )


def saved_chunks(db: Session, document_id: str) -> list[ChunkRead]:
    rows = db.scalars(select(DocumentChunk).where(DocumentChunk.doc_id == document_id).order_by(DocumentChunk.seq)).all()
    result = []
    end = 0
    for chunk in rows:
        result.append(chunk_read(chunk, end))
        end = chunk.start_offset + chunk.chars
    return result


def summary(db: Session, doc: KnowledgeDocument) -> DocumentSummary:
    count, vectors = db.execute(select(
        func.count(DocumentChunk.id),
        func.count(DocumentChunk.embedding),
    ).where(DocumentChunk.doc_id == doc.id)).one()
    return DocumentSummary(
        id=doc.id, kb_id=doc.kb_id, name=doc.name, type=doc.type, size=doc.size,
        source=doc.source, status=doc.status, error_message=doc.error_message,
        chunk_count=count, vector_count=vectors if doc.status == "vectorized" else 0,
        created_at=doc.created_at, updated_at=doc.updated_at,
    )


def list_documents(db: Session, q: str, kb_id: str | None, page: int, page_size: int) -> DocumentPage:
    statement = select(KnowledgeDocument)
    if q:
        statement = statement.where(KnowledgeDocument.name.contains(q, autoescape=True))
    if kb_id:
        statement = statement.where(KnowledgeDocument.kb_id == kb_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    stats = KnowledgeStats(
        documents=db.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0,
        pending=db.scalar(select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.status != "vectorized")) or 0,
        chunks=db.scalar(select(func.count()).select_from(DocumentChunk)) or 0,
        vectors=db.scalar(select(func.count(DocumentChunk.embedding)).join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.doc_id).where(
            DocumentChunk.vector_status == "ready", KnowledgeDocument.status == "vectorized")) or 0,
    )
    return DocumentPage(items=[summary(db, doc) for doc in rows], total=total, page=page, page_size=page_size, stats=stats)


def document_detail(db: Session, document_id: str) -> DocumentDetail:
    doc = find_document(db, document_id)
    return DocumentDetail(**summary(db, doc).model_dump(), content=doc.content, chunks=saved_chunks(db, document_id))


def parse_document_task(document_id: str, factory: sessionmaker, storage: LocalFileStorage):
    """使用独立事务执行解析；请求的数据库会话不会传入后台任务。"""
    with factory() as db:
        doc = db.get(KnowledgeDocument, document_id)
        if doc is None or doc.status != "parsing":
            return
        try:
            if not doc.object_key:
                raise ParseError("未找到原文件，请重新上传文档。")
            content = parse_file(storage.path(doc.object_key), doc.type)
            doc.content = content
            doc.status = "parsed"
            doc.error_message = None
        except Exception as exc:
            doc.status = "failed"
            doc.error_message = str(exc) if isinstance(exc, ParseError) else "解析失败，请检查原文件后重试。"
            logger.warning("Document parse failed (%s): %s", document_id, type(exc).__name__)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.error("Could not persist document parsing result (%s)", document_id)


def create_document(db: Session, storage: LocalFileStorage, stream, filename: str | None, kb_id: str, source: str) -> DocumentSummary:
    name, suffix = validate_filename(filename)
    if db.get(KnowledgeBase, kb_id) is None:
        raise BusinessError("知识库不存在，请先执行最新的数据库迁移。", 422)
    try:
        object_key, size = storage.save(stream, suffix)
    except OSError as exc:
        raise BusinessError("无法保存原文件，请检查上传目录的写入权限。", 503) from exc
    doc = KnowledgeDocument(
        id=uuid4().hex, kb_id=kb_id, name=name, type=suffix.upper(), size=size,
        source=source.strip() or "本地上传", status="parsing", object_key=object_key,
    )
    try:
        db.add(doc)
        db.flush()
        db.refresh(doc)
        result = summary(db, doc)
        db.commit()
    except Exception:
        db.rollback()
        storage.remove(object_key)
        raise
    return result


def retry_document(db: Session, document_id: str) -> DocumentSummary:
    doc = find_document(db, document_id, lock=True)
    now = datetime.now(UTC).replace(tzinfo=None)
    stale = doc.status == "parsing" and doc.updated_at < now - timedelta(minutes=10)
    if doc.status != "failed" and not stale:
        raise BusinessError("只有解析失败或解析超过 10 分钟的文档可以重试。", 409)
    doc.status = "parsing"
    doc.error_message = None
    doc.updated_at = now
    db.commit()
    return summary(db, doc)


def _delete_document(db: Session, storage: LocalFileStorage, document_id: str):
    doc = find_document(db, document_id, lock=True)
    if doc.status in {"parsing", "vectorizing"}:
        raise BusinessError("文档正在解析或向量化，请等待任务完成后再删除。", 409)
    # 先暂存原文件；数据库回滚时可恢复，提交后再清理暂存文件。
    original = storage.path(doc.object_key) if doc.object_key else None
    trash = original.with_suffix(original.suffix + ".deleting") if original else None
    try:
        if original and original.exists():
            original.replace(trash)
    except OSError as exc:
        raise BusinessError("原文件无法删除，请检查上传目录权限。", 503) from exc
    try:
        db.execute(update(VectorIndex).where(VectorIndex.kb_id == doc.kb_id).values(status="stale"))
        db.delete(doc)
        db.commit()
    except Exception:
        db.rollback()
        if original and trash and trash.exists():
            trash.replace(original)
        raise
    if trash:
        try:
            trash.unlink(missing_ok=True)
        except OSError:
            logger.warning("Deferred cleanup required for deleted upload (%s)", document_id)


def preview_chunks(db: Session, document_id: str, parameters: ChunkParameters) -> ChunkResult:
    doc = find_document(db, document_id)
    if doc.status not in {"parsed", "chunked", "vectorized"} or not doc.content:
        raise BusinessError("文档尚未成功解析，暂时不能切块。", 409)
    return split_text(doc.id, doc.content, parameters)


def _save_chunks(db: Session, document_id: str, parameters: ChunkParameters) -> ChunkResult:
    doc = find_document(db, document_id, lock=True)
    result = preview_chunks(db, document_id, parameters)
    if not result.count:
        raise BusinessError("没有可保存的文本块。", 422)
    db.execute(delete(DocumentChunk).where(DocumentChunk.doc_id == doc.id))
    rows = [DocumentChunk(
        doc_id=doc.id, kb_id=doc.kb_id, seq=chunk.seq, content=chunk.content,
        start_offset=chunk.start_offset, chars=chunk.chars, vector_status="pending",
    ) for chunk in result.chunks]
    db.add_all(rows)
    db.execute(update(VectorIndex).where(VectorIndex.kb_id == doc.kb_id).values(status="stale"))
    doc.status = "chunked"
    db.commit()
    # 新块 ID 由数据库生成，响应返回落库后的实际 ID。
    result.chunks = saved_chunks(db, document_id)
    return result


def delete_document(db: Session, storage: LocalFileStorage, document_id: str, manager=None):
    from app.services.vectorstore.index_manager import get_index_manager
    from app.services.vectorstore.locking import index_write_lock
    manager = manager or get_index_manager()
    with index_write_lock(manager.root):
        return _delete_document(db, storage, document_id)


def save_chunks(db: Session, document_id: str, parameters: ChunkParameters, manager=None):
    from app.services.vectorstore.index_manager import get_index_manager
    from app.services.vectorstore.locking import index_write_lock
    manager = manager or get_index_manager()
    with index_write_lock(manager.root):
        return _save_chunks(db, document_id, parameters)
