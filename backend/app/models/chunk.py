from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MYSQL_TABLE_OPTIONS, TimestampMixin


class DocumentChunk(TimestampMixin, Base):
    __tablename__ = "document_chunk"
    __table_args__ = (
        UniqueConstraint("doc_id", "seq", name="uq_document_chunk_doc_seq"),
        Index("ix_document_chunk_kb_vector_status", "kb_id", "vector_status"),
        Index("ft_document_chunk_content", "content", mysql_prefix="FULLTEXT", mysql_with_parser="ngram"),
        MYSQL_TABLE_OPTIONS,
    )

    # 与后续 FAISS IndexIDMap2 的 int64 ID 对齐。
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_document.id", ondelete="CASCADE"), nullable=False
    )
    kb_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_base.id", ondelete="RESTRICT"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    chars: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[bytes | None] = mapped_column(MEDIUMBLOB)
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    embedding_dim: Mapped[int | None] = mapped_column(Integer)
    vector_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
