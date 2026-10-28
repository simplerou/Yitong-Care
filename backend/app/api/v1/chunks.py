from typing import Annotated
from fastapi import APIRouter, Depends
from app.services.vectorstore.index_manager import IndexManager, get_index_manager

from app.core.deps import DatabaseSession
from app.core.exceptions import BusinessError
from app.models import DocumentChunk
from app.schemas.chunk import ChunkParameters, ChunkRead, ChunkResult
from app.services.document_service import chunk_read, preview_chunks, save_chunks

Manager = Annotated[IndexManager, Depends(get_index_manager)]
router = APIRouter(tags=["chunks"])


@router.post("/documents/{document_id}/chunks:preview", response_model=ChunkResult)
def preview(document_id: str, parameters: ChunkParameters, db: DatabaseSession):
    return preview_chunks(db, document_id, parameters)


@router.post("/documents/{document_id}/chunks", response_model=ChunkResult)
def save(document_id: str, parameters: ChunkParameters, db: DatabaseSession, manager: Manager):
    return save_chunks(db, document_id, parameters, manager)


@router.get("/chunks/{chunk_id}", response_model=ChunkRead)
def detail(chunk_id: int, db: DatabaseSession):
    chunk = db.get(DocumentChunk, chunk_id)
    if chunk is None:
        raise BusinessError("文本块不存在或已重新切分。", 404)
    return chunk_read(chunk)
