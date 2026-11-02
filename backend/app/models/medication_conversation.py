from sqlalchemy import ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MYSQL_TABLE_OPTIONS, TimestampMixin


class MedicationConversation(TimestampMixin, Base):
    __tablename__ = 'medication_conversation'
    __table_args__ = (Index('ix_medication_conversation_updated', 'updated_at'), MYSQL_TABLE_OPTIONS)
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    # Minimal profile: age, conditions, allergies. Never identity or prescription numbers.
    profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class MedicationTurn(TimestampMixin, Base):
    __tablename__ = 'medication_turn'
    __table_args__ = (UniqueConstraint('conversation_id', 'seq', name='uq_medication_turn_conversation_seq'), MYSQL_TABLE_OPTIONS)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('medication_conversation.id', ondelete='CASCADE'), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
