"""Persist policy conversations and immutable answer/source snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
revision='20261029_0005'
down_revision='20261028_0004'
branch_labels=None
depends_on=None
OPTIONS={'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_0900_ai_ci'}


def timestamps():
    return [sa.Column('created_at',sa.DateTime(),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at',sa.DateTime(),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP'))]


def upgrade():
    op.create_table('policy_conversation',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('title',sa.String(100),nullable=False),*timestamps(),**OPTIONS)
    op.create_index('ix_policy_conversation_updated','policy_conversation',['updated_at'])
    op.create_table('policy_turn',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('conversation_id',sa.String(36),sa.ForeignKey('policy_conversation.id',ondelete='CASCADE'),nullable=False),
        sa.Column('seq',sa.Integer(),nullable=False),sa.Column('question',mysql.LONGTEXT(),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),sa.Column('attempts',sa.Integer(),nullable=False),
        sa.Column('response',sa.JSON(),nullable=True),sa.Column('error',sa.String(500),nullable=True),*timestamps(),
        sa.UniqueConstraint('conversation_id','seq',name='uq_policy_turn_conversation_seq'),**OPTIONS)


def downgrade():
    op.drop_table('policy_turn')
    op.drop_index('ix_policy_conversation_updated',table_name='policy_conversation')
    op.drop_table('policy_conversation')
