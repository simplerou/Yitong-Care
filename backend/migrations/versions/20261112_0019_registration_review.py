"""Pending role applications; existing accounts remain active."""
from alembic import op
import sqlalchemy as sa
revision='20261112_0019'
down_revision='20261112_0018'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('account',sa.Column('status',sa.String(16),nullable=False,server_default='active'))
    op.add_column('account',sa.Column('requested_role',sa.String(16),nullable=True))
    op.add_column('account',sa.Column('application_note',sa.String(500),nullable=False,server_default=''))
    op.add_column('account',sa.Column('review_note',sa.String(1000),nullable=False,server_default=''))
    op.add_column('account',sa.Column('application_version',sa.Integer(),nullable=False,server_default='1'))
    op.add_column('account',sa.Column('reviewed_at',sa.DateTime(),nullable=True))
def downgrade():
    for name in ['reviewed_at','application_version','review_note','application_note','requested_role','status']:op.drop_column('account',name)
