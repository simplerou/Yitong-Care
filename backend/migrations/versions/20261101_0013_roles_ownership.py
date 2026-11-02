"""Admin role and private agent conversations; preserve legacy data for explicit claim."""
from alembic import op
import sqlalchemy as sa
revision = '20261101_0013'
down_revision = '20261101_0012'
branch_labels = None
depends_on = None
TABLES = ['policy_conversation','health_conversation','medication_conversation','diet_conversation','safety_conversation','mind_conversation']
def upgrade():
    op.add_column('account',sa.Column('role',sa.String(16),nullable=False,server_default='user'))
    for table in TABLES:
        op.add_column(table,sa.Column('owner_id',sa.String(36),nullable=True))
        op.create_index('ix_'+table+'_owner_id',table,['owner_id'])
def downgrade():
    for table in reversed(TABLES):
        op.drop_index('ix_'+table+'_owner_id',table_name=table)
        op.drop_column(table,'owner_id')
    op.drop_column('account','role')
