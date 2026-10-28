"""Seed the default knowledge base for document uploads."""
from alembic import op
import sqlalchemy as sa

revision = "20261028_0002"
down_revision = "20261028_0001"
branch_labels = None
depends_on = None


def upgrade():
    table = sa.table("knowledge_base", sa.column("id", sa.String), sa.column("name", sa.String))
    op.bulk_insert(table, [{"id": "general", "name": "通用知识库"}])


def downgrade():
    # 有文档时外键会拒绝删除，避免降级误删业务数据。
    op.execute(sa.text("DELETE FROM knowledge_base WHERE id = 'general'"))
