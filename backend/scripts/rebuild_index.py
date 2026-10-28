"""离线从数据库重建当前 Embedding 配置的索引，无需调用模型。"""
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.models import KnowledgeBase
from app.services.embedding_service import require_no_active_task
from app.services.vectorstore.index_manager import get_index_manager
from app.services.vectorstore.locking import index_write_lock


def main():
    settings = get_settings(); manager = get_index_manager()
    if not settings.embedding_model: raise SystemExit('请先配置 EMBEDDING_MODEL 和 EMBEDDING_DIMENSIONS。')
    try:
        with index_write_lock(manager.root):
            with SessionLocal() as db:
                require_no_active_task(db)
                for kb_id in db.scalars(select(KnowledgeBase.id)).all():
                    record = manager.rebuild(db,kb_id,settings.embedding_key,settings.embedding_dimensions)
                    print(f'{kb_id}: v{record.version}, {record.vector_count} 条向量')
                db.commit()
    finally:
        engine.dispose()


if __name__ == '__main__': main()
