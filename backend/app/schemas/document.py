from datetime import UTC, datetime

from pydantic import BaseModel, field_serializer

from app.schemas.chunk import ChunkRead


class KnowledgeBaseRead(BaseModel):
    id: str
    name: str


class DocumentSummary(BaseModel):
    id: str
    kb_id: str
    name: str
    type: str
    size: int
    source: str | None
    status: str
    error_message: str | None
    chunk_count: int
    vector_count: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        return value.replace(tzinfo=UTC).isoformat()


class DocumentDetail(DocumentSummary):
    content: str | None
    chunks: list[ChunkRead]


class KnowledgeStats(BaseModel):
    documents: int
    chunks: int
    vectors: int
    pending: int


class DocumentPage(BaseModel):
    items: list[DocumentSummary]
    total: int
    page: int
    page_size: int
    stats: KnowledgeStats
