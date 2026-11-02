"""Resident records, care assignments and immutable change snapshots."""
from alembic import op
import sqlalchemy as sa
revision='20261102_0014'
down_revision='20261101_0013'
branch_labels=None
depends_on=None
OPTIONS={'mysql_engine':'InnoDB','mysql_charset':'utf8mb4','mysql_collate':'utf8mb4_0900_ai_ci'}
def timestamps():
    return [sa.Column('created_at',sa.DateTime(),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),sa.Column('updated_at',sa.DateTime(),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP'))]
def upgrade():
    fields=[sa.Column('id',sa.String(36),primary_key=True),sa.Column('record_no',sa.String(20),nullable=False,unique=True)]
    for name,size in [('name',50),('gender',16),('status',16),('location',100),('care_level',30),('contact_name',50),('contact_relation',30),('contact_phone',32),('source',200)]:
        fields.append(sa.Column(name,sa.String(size),nullable=False))
    for name in ['birth_date','admission_date']: fields.append(sa.Column(name,sa.Date(),nullable=True))
    for name in ['allergies','chronic_conditions','dietary_notes','mobility_notes','communication_notes','care_notes']: fields.append(sa.Column(name,sa.Text(),nullable=False))
    op.create_table('resident',*fields,sa.Column('version',sa.Integer(),nullable=False),*timestamps(),**OPTIONS)
    op.create_index('ix_resident_name','resident',['name'])
    op.create_table('resident_assignment',sa.Column('resident_id',sa.String(36),sa.ForeignKey('resident.id',ondelete='CASCADE'),primary_key=True),sa.Column('account_id',sa.String(36),sa.ForeignKey('account.id'),primary_key=True),**OPTIONS)
    op.create_table('resident_change',sa.Column('id',sa.String(36),primary_key=True),sa.Column('resident_id',sa.String(36),sa.ForeignKey('resident.id'),nullable=False),sa.Column('actor_id',sa.String(36),sa.ForeignKey('account.id'),nullable=False),sa.Column('actor_name',sa.String(30),nullable=False),sa.Column('reason',sa.String(300),nullable=False),sa.Column('before',sa.JSON(),nullable=True),sa.Column('after',sa.JSON(),nullable=False),*timestamps(),**OPTIONS)
    op.create_index('ix_resident_change_resident_id','resident_change',['resident_id'])
def downgrade():
    op.drop_table('resident_change')
    op.drop_table('resident_assignment')
    op.drop_table('resident')
