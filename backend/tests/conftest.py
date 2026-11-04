from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, Integer, LargeBinary, MetaData, Text, create_engine, event
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMBLOB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services.conversations import get_conversation_lock_dir
from app.core.deps import get_session_factory
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models import KnowledgeBase
from app.services.storage import LocalFileStorage, get_storage
from app.services.vectorstore.index_manager import IndexManager, get_index_manager


@pytest.fixture()
def client(tmp_path):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)

    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')

    # 测试中映射 MySQL 专用类型；生产模型与迁移仍使用 MySQL 类型和 ngram。
    metadata = MetaData()
    for original in Base.metadata.sorted_tables:
        table = original.to_metadata(metadata)
        for column in table.columns:
            if isinstance(column.type, LONGTEXT):
                column.type = Text()
            elif isinstance(column.type, MEDIUMBLOB):
                column.type = LargeBinary()
            elif isinstance(column.type, BigInteger):
                column.type = Integer()
        if 'id' in table.c and isinstance(table.c.id.type, Integer) and table.c.id.primary_key:
            table.dialect_options['sqlite']['autoincrement'] = True
    metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        # Mirror the six agent knowledge bases plus the default one.
        for kb_id, name in [('general', '通用知识库'), ('policy', '政策法规库'), ('health', '健康管理库'),
                            ('medication', '用药安全库'), ('diet', '膳食营养库'), ('safety', '居家安全库'),
                            ('mind', '心理关怀库')]:
            db.add(KnowledgeBase(id=kb_id, name=name))
        db.commit()
    storage = LocalFileStorage(tmp_path / 'uploads', max_bytes=1024)
    app = create_app()

    def database():
        with factory() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_index_manager] = lambda: IndexManager(tmp_path / 'faiss')
    from app.services.menu_diagnostics import get_menu_diagnostic_dir
    app.dependency_overrides[get_menu_diagnostic_dir] = lambda: tmp_path/'menu_diagnostics'
    app.dependency_overrides[get_conversation_lock_dir] = lambda: tmp_path/'conversation_locks'
    with TestClient(app) as test_client:
        test_client.post('/api/auth/register', json={'phone':'13800000000','name':'测试用户','password':'Test12345'})
        from app.models.auth import Account
        from sqlalchemy import select
        with factory() as db:
            db.scalar(select(Account).where(Account.phone=='13800000000')).role='admin'
            db.commit()
        login = test_client.post('/api/auth/login', json={'phone':'13800000000','password':'Test12345'})
        assert login.status_code == 200, login.text
        test_client.headers['Authorization'] = 'Bearer ' + login.json()['token']
        yield test_client, storage, factory
    engine.dispose()
