"""One-to-one resident login binding, explicit resident role stored on account."""
from alembic import op
import sqlalchemy as sa
revision='20261102_0015'
down_revision='20261102_0014'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('resident_account_binding',sa.Column('resident_id',sa.String(36),sa.ForeignKey('resident.id'),primary_key=True),sa.Column('account_id',sa.String(36),sa.ForeignKey('account.id'),nullable=False,unique=True),sa.Column('created_at',sa.DateTime(),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),sa.Column('updated_at',sa.DateTime(),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),mysql_engine='InnoDB',mysql_charset='utf8mb4',mysql_collate='utf8mb4_0900_ai_ci')

def downgrade():
    # Do not silently turn formerly-bound resident accounts into staff users.
    op.drop_table('resident_account_binding')
