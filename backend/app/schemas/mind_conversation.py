from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.schemas.mind import MindAnswer, MindDialogueState, MindProfile


class MindTimeRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at')
    def time(self, value):
        return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()


class MindConversationRecord(MindTimeRecord):
    profile: MindProfile | None = None
    id: str
    title: str


class MindStoredTurn(MindTimeRecord):
    id: str
    conversation_id: str
    seq: int
    question: str
    status: Literal['running', 'succeeded', 'failed']
    stage: str | None = None
    attempts: int
    response: MindAnswer | None
    error: str | None


class MindConversationQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    question: str = Field(min_length=1, max_length=1000)
    retry: bool = False

    @field_validator('question')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('请输入问题')
        return value.strip()


class MindProfileUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    profile: MindProfile = Field(default_factory=MindProfile)
    dialogue_state: MindDialogueState | None = None
