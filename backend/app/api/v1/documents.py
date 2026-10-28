from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.deps import DatabaseSession, get_session_factory
from app.models import KnowledgeBase
from app.schemas.document import DocumentDetail, DocumentPage, DocumentSummary, KnowledgeBaseRead
from app.services import document_service
from app.services.storage import LocalFileStorage, get_storage

from app.services.vectorstore.index_manager import IndexManager, get_index_manager

Manager = Annotated[IndexManager, Depends(get_index_manager)]
router = APIRouter(tags=["knowledge"])
Storage = Annotated[LocalFileStorage, Depends(get_storage)]
SessionFactory = Annotated[sessionmaker, Depends(get_session_factory)]


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseRead])
def knowledge_bases(db: DatabaseSession):
    return [{"id": kb.id, "name": kb.name} for kb in db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.name))]


@router.get("/documents", response_model=DocumentPage)
def documents(
    db: DatabaseSession, q: str = Query(default="", max_length=100),
    kb_id: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
):
    return document_service.list_documents(db, q.strip(), kb_id, page, page_size)


@router.post("/documents", response_model=DocumentSummary, status_code=202)
def upload_document(
    background_tasks: BackgroundTasks, db: DatabaseSession, storage: Storage, factory: SessionFactory,
    file: UploadFile = File(...), kb_id: str = Form(default="general", max_length=64),
    source: str = Form(default="本地上传", max_length=512),
):
    try:
        result = document_service.create_document(db, storage, file.file, file.filename, kb_id, source)
    finally:
        file.file.close()
    background_tasks.add_task(document_service.parse_document_task, result.id, factory, storage)
    return result


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def document(document_id: str, db: DatabaseSession):
    return document_service.document_detail(db, document_id)


@router.post("/documents/{document_id}/parse:retry", response_model=DocumentSummary, status_code=202)
def retry(document_id: str, background_tasks: BackgroundTasks, db: DatabaseSession, storage: Storage, factory: SessionFactory):
    result = document_service.retry_document(db, document_id)
    background_tasks.add_task(document_service.parse_document_task, document_id, factory, storage)
    return result


@router.delete("/documents/{document_id}", status_code=204)
def remove(document_id: str, db: DatabaseSession, storage: Storage, manager: Manager):
    document_service.delete_document(db, storage, document_id, manager)
    return Response(status_code=204)
