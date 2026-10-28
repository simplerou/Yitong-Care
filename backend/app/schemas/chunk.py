from pydantic import BaseModel, Field, model_validator


class ChunkParameters(BaseModel):
    size: int = Field(default=220, ge=100, le=500)
    overlap: int = Field(default=30, ge=0, le=100)

    @model_validator(mode="after")
    def valid_overlap(self):
        if self.overlap >= self.size:
            raise ValueError("重叠长度必须小于切块大小")
        return self


class ChunkRead(BaseModel):
    id: int | None = None
    doc_id: str
    seq: int
    content: str
    start_offset: int
    chars: int
    vector_status: str = "pending"
    overlap_chars: int = 0


class ChunkResult(BaseModel):
    doc_id: str
    count: int
    average_chars: int
    chunks: list[ChunkRead]
