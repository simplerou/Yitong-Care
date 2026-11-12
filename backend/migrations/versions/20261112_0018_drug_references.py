"""Versioned drug-specific insert references with canonical chunk offsets."""
from alembic import op
import sqlalchemy as sa
revision='20261112_0018'
down_revision='20261112_0017'
branch_labels=None
depends_on=None
OPT={'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_0900_ai_ci'}
def upgrade():
    op.create_table('ops_drug_reference',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('drug_id',sa.String(80),nullable=False),
        sa.Column('category',sa.String(24),nullable=False),sa.Column('chunk_id',sa.BigInteger(),sa.ForeignKey('document_chunk.id',ondelete='CASCADE'),nullable=False),
        sa.Column('section',sa.String(100),nullable=False),sa.Column('valid_from',sa.Date(),nullable=False),sa.Column('valid_until',sa.Date(),nullable=True),sa.Column('source_hash',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),sa.Column('updated_at',sa.DateTime(),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),**OPT)
    op.create_index('ix_ops_drug_reference_drug_id','ops_drug_reference',['drug_id'])
def downgrade():op.drop_table('ops_drug_reference')
