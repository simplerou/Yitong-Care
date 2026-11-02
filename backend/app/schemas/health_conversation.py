from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.schemas.health import HealthAnswer, HealthDialogueState, HealthProfile


class HealthTimeRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at')
    def time(self, value):
        return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()


class HealthConversationRecord(HealthTimeRecord):
    profile: HealthProfile | None = None
    id: str
    title: str


class HealthStoredTurn(HealthTimeRecord):
    id: str
    conversation_id: str
    seq: int
    question: str
    status: Literal['running', 'succeeded', 'failed']
    stage: str | None = None
    attempts: int
    response: HealthAnswer | None
    error: str | None


class HealthConversationQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    question: str = Field(min_length=1, max_length=1000)
    retry: bool = False

    @field_validator('question')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('请输入问题')
        return value.strip()


class HealthConversationDetail(BaseModel):
    conversation: HealthConversationRecord
    turns: list[HealthStoredTurn]
    has_more: bool
    next_before_seq: int | None


class HealthProgress(BaseModel):
    request_id: str
    status: str
    stage: str | None


class HealthProfileUpdate(BaseModel):
    """Optional saved profile. Deliberately excludes identity and contact fields."""
    model_config = ConfigDict(extra='forbid')
    profile: HealthProfile = Field(default_factory=HealthProfile)
    dialogue_state: HealthDialogueState | None = None
