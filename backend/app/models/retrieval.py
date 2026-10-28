from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MYSQL_TABLE_OPTIONS, TimestampMixin


class RetrievalLog(TimestampMixin, Base):
    __tablename__ = "retrieval_log"
    __table_args__ = (Index("ix_retrieval_log_created_at", "created_at"), MYSQL_TABLE_OPTIONS)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="legacy_weighted", server_default="legacy_weighted")
    query: Mapped[str] = mapped_column(String(1000), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    took_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)


class RetrievalHit(Base):
    __tablename__ = "retrieval_hit"
    __table_args__ = (UniqueConstraint("log_id", "rank", name="uq_retrieval_hit_log_rank"), MYSQL_TABLE_OPTIONS)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    log_id: Mapped[str] = mapped_column(ForeignKey("retrieval_log.id", ondelete="CASCADE"), nullable=False)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("document_chunk.id", ondelete="SET NULL"))
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
