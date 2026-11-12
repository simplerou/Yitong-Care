"""Medical signatures and persistent internal medical exception inbox."""
from alembic import op
import sqlalchemy as sa
revision='20261112_0020'
down_revision='20261112_0019'
branch_labels=None
depends_on=None
OPT={'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_0900_ai_ci'}
def upgrade():
    op.add_column('ops_draft',sa.Column('professional_signoff',sa.JSON(),nullable=True))
    op.create_table('ops_medical_inbox',sa.Column('id',sa.String(36),primary_key=True),sa.Column('draft_id',sa.String(36),sa.ForeignKey('ops_draft.id'),nullable=False,unique=True),sa.Column('resident_id',sa.String(36),sa.ForeignKey('resident.id'),nullable=False),sa.Column('severity',sa.String(16),nullable=False),sa.Column('observation',sa.String(2000),nullable=False),sa.Column('status',sa.String(16),nullable=False),sa.Column('handled_by',sa.String(36),sa.ForeignKey('account.id'),nullable=True),sa.Column('handling_note',sa.String(1000),nullable=False),sa.Column('created_at',sa.DateTime(),server_default=sa.text('CURRENT_TIMESTAMP'),nullable=False),sa.Column('updated_at',sa.DateTime(),server_default=sa.text('CURRENT_TIMESTAMP'),nullable=False),**OPT)
def downgrade():
    op.drop_table('ops_medical_inbox');op.drop_column('ops_draft','professional_signoff')
