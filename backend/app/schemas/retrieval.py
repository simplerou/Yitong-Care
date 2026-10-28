from datetime import UTC, datetime
from typing import Literal
from pydantic import BaseModel, Field, field_serializer, field_validator


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    scope: str = Field(default='all', min_length=1, max_length=64)
    top_k: Literal[3, 5, 10] = 5
    threshold: float = Field(default=.12, ge=.02, le=.6, description="语义召回余弦下限；BM25 独立召回，不过滤 RRF 分数")

    @field_validator('query')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('请输入检索内容')
        return value.strip()


class SearchHit(BaseModel):
    chunk_id: int
    doc_id: str
    kb_id: str
    doc_name: str
    type: str
    source: str
    seq: int
    start: int
    end: int
    chars: int
    text: str
    score: float
    cos: float
    bm25_score: float | None = None
    semantic_rank: int | None = None
    bm25_rank: int | None = None
    lexical_score: float


class SearchResult(BaseModel):
    strategy: str = "legacy_weighted"
    log_id: str
    query: str
    scope: str
    top_k: int
    threshold: float
    took_ms: int
    vector_count: int
    model: str
    hits: list[SearchHit]
    historical: bool = False


class RetrievalRecord(BaseModel):
    strategy: str = "legacy_weighted"
    id: str
    query: str
    scope: str
    top_k: int
    threshold: float
    took_ms: int
    hit_count: int
    top_score: float | None
    top_source: str | None
    created_at: datetime

    @field_serializer('created_at')
    def serialize_time(self, value):
        return value.replace(tzinfo=UTC).isoformat()
