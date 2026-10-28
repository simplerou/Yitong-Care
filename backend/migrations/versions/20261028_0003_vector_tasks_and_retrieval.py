"""Add embedding jobs, index checksums and persistent retrieval records."""
from alembic import op
import sqlalchemy as sa

revision = '20261028_0003'
down_revision = '20261028_0002'
branch_labels = None
depends_on = None
OPTIONS = {'mysql_engine':'InnoDB', 'mysql_charset':'utf8mb4', 'mysql_collate':'utf8mb4_0900_ai_ci'}


def timestamps():
    return [sa.Column('created_at',sa.DateTime(),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at',sa.DateTime(),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP'))]


def upgrade():
    op.add_column('vector_index',sa.Column('sha256',sa.String(64),nullable=True))
    op.create_table('embedding_task',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('doc_id',sa.String(64),nullable=False),sa.Column('model',sa.String(128),nullable=False),
        sa.Column('model_name',sa.String(80),nullable=False),sa.Column('dim',sa.Integer(),nullable=False),
        sa.Column('batch_size',sa.Integer(),nullable=False),sa.Column('status',sa.String(32),nullable=False),
        sa.Column('phase',sa.String(32),nullable=False),sa.Column('progress',sa.Integer(),nullable=False),
        sa.Column('total',sa.Integer(),nullable=False),sa.Column('processed',sa.Integer(),nullable=False),
        sa.Column('chunk_ids',sa.JSON(),nullable=False),sa.Column('log',sa.JSON(),nullable=False),
        sa.Column('error_message',sa.String(1024)),sa.Column('index_version',sa.BigInteger()),*timestamps(),
        sa.ForeignKeyConstraint(['doc_id'],['knowledge_document.id'],name='fk_embedding_task_doc_id_knowledge_document',ondelete='CASCADE'),**OPTIONS)
    op.create_index('ix_embedding_task_doc_status','embedding_task',['doc_id','status'])
    op.create_table('retrieval_log',
        sa.Column('id',sa.String(64),primary_key=True),sa.Column('query',sa.String(1000),nullable=False),
        sa.Column('scope',sa.String(64),nullable=False),sa.Column('top_k',sa.Integer(),nullable=False),
        sa.Column('threshold',sa.Float(),nullable=False),sa.Column('took_ms',sa.Integer(),nullable=False),
        sa.Column('hit_count',sa.Integer(),nullable=False),sa.Column('vector_count',sa.BigInteger(),nullable=False),
        sa.Column('model',sa.String(128),nullable=False),*timestamps(),**OPTIONS)
    op.create_index('ix_retrieval_log_created_at','retrieval_log',['created_at'])
    op.create_table('retrieval_hit',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('log_id',sa.String(64),nullable=False),sa.Column('chunk_id',sa.BigInteger(),nullable=True),
        sa.Column('rank',sa.Integer(),nullable=False),sa.Column('score',sa.Float(),nullable=False),
        sa.Column('snapshot',sa.JSON(),nullable=False),
        sa.ForeignKeyConstraint(['log_id'],['retrieval_log.id'],name='fk_retrieval_hit_log_id_retrieval_log',ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chunk_id'],['document_chunk.id'],name='fk_retrieval_hit_chunk_id_document_chunk',ondelete='SET NULL'),
        sa.UniqueConstraint('log_id','rank',name='uq_retrieval_hit_log_rank'),**OPTIONS)


def downgrade():
    op.drop_table('retrieval_hit');op.drop_table('retrieval_log');op.drop_table('embedding_task')
    op.drop_column('vector_index','sha256')
