from datetime import UTC, datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from app.schemas.chat import PolicyAnswer


class TimeRecord(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at','updated_at')
    def time(self,value):
        return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()


class ConversationRecord(TimeRecord):
    id: str
    title: str


class StoredTurn(TimeRecord):
    id: str
    conversation_id: str
    seq: int
    question: str
    status: Literal['running','succeeded','failed']
    attempts: int
    response: PolicyAnswer | None
    error: str | None


class ConversationQuestion(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID
    question: str=Field(min_length=1,max_length=1000)
    retry: bool=False

    @field_validator('question')
    @classmethod
    def nonblank(cls,value):
        if not value.strip(): raise ValueError('请输入问题')
        return value.strip()
