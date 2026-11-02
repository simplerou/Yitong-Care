"""Accounts and expiring server-side login sessions."""
from alembic import op
import sqlalchemy as sa
revision = '20261101_0012'
down_revision = '20261101_0011'
branch_labels = None
depends_on = None
OPTIONS = {'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_0900_ai_ci'}
def upgrade():
    op.create_table('account', sa.Column('id',sa.String(36),primary_key=True), sa.Column('phone',sa.String(11),nullable=False,unique=True), sa.Column('name',sa.String(30),nullable=False), sa.Column('password_hash',sa.String(256),nullable=False), **OPTIONS)
    op.create_table('login_session', sa.Column('token_hash',sa.String(64),primary_key=True), sa.Column('account_id',sa.String(36),sa.ForeignKey('account.id',ondelete='CASCADE'),nullable=False), sa.Column('expires_at',sa.DateTime(),nullable=False), **OPTIONS)
def downgrade():
    op.drop_table('login_session')
    op.drop_table('account')
