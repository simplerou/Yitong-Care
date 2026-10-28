from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MYSQL_TABLE_OPTIONS, TimestampMixin


class KnowledgeDocument(TimestampMixin, Base):
    __tablename__ = "knowledge_document"
    __table_args__ = (
        Index("ix_knowledge_document_kb_status", "kb_id", "status"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kb_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_base.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    source: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="parsed", server_default="parsed"
    )
    content: Mapped[str | None] = mapped_column(LONGTEXT)
    object_key: Mapped[str | None] = mapped_column(String(1024))
    error_message: Mapped[str | None] = mapped_column(String(1024))
