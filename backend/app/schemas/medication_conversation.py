from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.schemas.medication import MedicationAnswer, MedicationDialogueState, MedicationProfile


class MedicationTimeRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at')
    def time(self, value):
        return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()


class MedicationConversationRecord(MedicationTimeRecord):
    profile: MedicationProfile | None = None
    id: str
    title: str


class MedicationStoredTurn(MedicationTimeRecord):
    id: str
    conversation_id: str
    seq: int
    question: str
    status: Literal['running', 'succeeded', 'failed']
    stage: str | None = None
    attempts: int
    response: MedicationAnswer | None
    error: str | None


class MedicationConversationQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    question: str = Field(min_length=1, max_length=1000)
    retry: bool = False

    @field_validator('question')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('请输入问题')
        return value.strip()


class MedicationProfileUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    profile: MedicationProfile = Field(default_factory=MedicationProfile)
    dialogue_state: MedicationDialogueState | None = None
