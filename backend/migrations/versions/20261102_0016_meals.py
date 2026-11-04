"""Weekly menus, reviewed dietary requirements, selections and audit."""
from alembic import op
import sqlalchemy as sa
revision='20261102_0016'
down_revision='20261102_0015'
branch_labels=None
depends_on=None
OPT={'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_0900_ai_ci'}
def stamps():return [sa.Column(n,sa.DateTime(),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')) for n in ['created_at','updated_at']]
def upgrade():
    op.create_table('weekly_menu',sa.Column('id',sa.String(36),primary_key=True),sa.Column('week_start',sa.Date(),nullable=False,unique=True),sa.Column('status',sa.String(16),nullable=False),sa.Column('version',sa.Integer(),nullable=False),sa.Column('data',sa.JSON(),nullable=False),*stamps(),**OPT)
    op.create_table('meal_profile',sa.Column('resident_id',sa.String(36),sa.ForeignKey('resident.id'),primary_key=True),sa.Column('resident_version',sa.Integer(),nullable=False),sa.Column('version',sa.Integer(),nullable=False),sa.Column('data',sa.JSON(),nullable=False),*stamps(),**OPT)
    op.create_table('meal_selection',sa.Column('id',sa.String(36),primary_key=True),sa.Column('resident_id',sa.String(36),sa.ForeignKey('resident.id'),nullable=False),sa.Column('menu_id',sa.String(36),sa.ForeignKey('weekly_menu.id'),nullable=False),sa.Column('meal_date',sa.Date(),nullable=False),sa.Column('meal',sa.String(16),nullable=False),sa.Column('option_id',sa.String(36),nullable=False),*[sa.Column(k,sa.Integer(),nullable=False) for k in ['version','profile_version','resident_version']],*stamps(),sa.UniqueConstraint('resident_id','meal_date','meal',name='uq_meal_selection_resident_slot'),**OPT)
    op.create_table('meal_change',sa.Column('id',sa.String(36),primary_key=True),sa.Column('actor_id',sa.String(36),sa.ForeignKey('account.id'),nullable=False),sa.Column('kind',sa.String(30),nullable=False),sa.Column('entity_id',sa.String(36),nullable=False),sa.Column('data',sa.JSON(),nullable=False),*stamps(),**OPT)
def downgrade():
    for table in ['meal_change','meal_selection','meal_profile','weekly_menu']:op.drop_table(table)
