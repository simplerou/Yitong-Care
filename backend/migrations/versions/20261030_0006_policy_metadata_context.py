"""Policy metadata, explicit consultation context, and execution stage."""
from alembic import op
import sqlalchemy as sa
revision='20261030_0006'
down_revision='20261029_0005'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('knowledge_document',sa.Column('policy_metadata',sa.JSON(),nullable=True))
    op.add_column('policy_conversation',sa.Column('context',sa.JSON(),nullable=True))
    op.add_column('policy_turn',sa.Column('stage',sa.String(32),nullable=True))


def downgrade():
    op.drop_column('policy_turn','stage')
    op.drop_column('policy_conversation','context')
    op.drop_column('knowledge_document','policy_metadata')
