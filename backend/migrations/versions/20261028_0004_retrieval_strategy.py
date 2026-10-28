"""Preserve legacy score semantics when switching to BM25/RRF."""
from alembic import op
import sqlalchemy as sa
revision = '20261028_0004'
down_revision = '20261028_0003'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('retrieval_log', sa.Column('strategy', sa.String(32), nullable=False, server_default='legacy_weighted'))

def downgrade():
    op.drop_column('retrieval_log', 'strategy')
