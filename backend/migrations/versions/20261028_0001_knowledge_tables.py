"""Create the initial MySQL knowledge tables.

Revision ID: 20261028_0001
Revises: None
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "20261028_0001"
down_revision = None
branch_labels = None
depends_on = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    ]


def upgrade():
    op.create_table(
        "knowledge_base",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_base"),
        sa.UniqueConstraint("name", name="uq_knowledge_base_name"),
        **TABLE_OPTIONS,
    )
    op.create_table(
        "knowledge_document",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("kb_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(512)),
        sa.Column("status", sa.String(32), nullable=False, server_default="parsed"),
        sa.Column("content", mysql.LONGTEXT()),
        sa.Column("object_key", sa.String(1024)),
        sa.Column("error_message", sa.String(1024)),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_document"),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_base.id"], ondelete="RESTRICT", name="fk_knowledge_document_kb_id_knowledge_base"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_knowledge_document_kb_status", "knowledge_document", ["kb_id", "status"])
    op.create_table(
        "document_chunk",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("doc_id", sa.String(64), nullable=False),
        sa.Column("kb_id", sa.String(64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("chars", sa.Integer(), nullable=False),
        sa.Column("embedding", mysql.MEDIUMBLOB()),
        sa.Column("embedding_model", sa.String(128)),
        sa.Column("embedding_dim", sa.Integer()),
        sa.Column("vector_status", sa.String(32), nullable=False, server_default="pending"),
        *timestamps(),
        sa.ForeignKeyConstraint(["doc_id"], ["knowledge_document.id"], ondelete="CASCADE", name="fk_document_chunk_doc_id_knowledge_document"),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_base.id"], ondelete="RESTRICT", name="fk_document_chunk_kb_id_knowledge_base"),
        sa.UniqueConstraint("doc_id", "seq", name="uq_document_chunk_doc_seq"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_document_chunk_kb_vector_status", "document_chunk", ["kb_id", "vector_status"])
    op.create_index("ft_document_chunk_content", "document_chunk", ["content"], mysql_prefix="FULLTEXT", mysql_with_parser="ngram")
    op.create_table(
        "vector_index",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kb_id", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False, server_default="cosine"),
        sa.Column("vector_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="building"),
        sa.Column("built_at", sa.DateTime()),
        *timestamps(),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_base.id"], ondelete="RESTRICT", name="fk_vector_index_kb_id_knowledge_base"),
        sa.UniqueConstraint("kb_id", "model", "version", name="uq_vector_index_kb_model_version"),
        **TABLE_OPTIONS,
    )


def downgrade():
    op.drop_table("vector_index")
    op.drop_index("ft_document_chunk_content", table_name="document_chunk")
    op.drop_index("ix_document_chunk_kb_vector_status", table_name="document_chunk")
    op.drop_table("document_chunk")
    op.drop_index("ix_knowledge_document_kb_status", table_name="knowledge_document")
    op.drop_table("knowledge_document")
    op.drop_table("knowledge_base")
