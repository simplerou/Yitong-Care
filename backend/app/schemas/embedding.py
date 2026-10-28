from typing import Literal
from pydantic import BaseModel


class EmbeddingRequest(BaseModel):
    model: str | None = None
    batch_size: Literal[8, 16, 32] = 16


class EmbeddingTaskRead(BaseModel):
    id: int
    doc_id: str
    model: str
    model_name: str
    dimensions: int
    batch_size: int
    status: str
    phase: str
    progress: int
    total: int
    processed: int
    log: list[str]
    error_message: str | None
    index_version: int | None
