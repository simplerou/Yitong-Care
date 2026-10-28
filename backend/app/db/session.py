from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def build_engine(settings: Settings) -> Engine:
    engine = create_engine(
        settings.database_url(),
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=settings.mysql_pool_size,
        max_overflow=settings.mysql_max_overflow,
        pool_timeout=10,
        connect_args={
            "connect_timeout": settings.mysql_connect_timeout,
            "read_timeout": 10,
            "write_timeout": 10,
        },
        hide_parameters=True,
    )

    @event.listens_for(engine, "connect")
    def set_session_timezone(dbapi_connection, _connection_record):
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")

    return engine


# 创建连接池不会立刻连接 MySQL；健康检查/业务请求时才实际连接。
engine = build_engine(get_settings())
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
