from logging.config import fileConfig
from pathlib import Path
import sys

# 支持从工程根目录通过 -c backend/alembic.ini 执行，且兼容目录名中的空格。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import context

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import build_engine
from app import models  # noqa: F401 注册所有映射表，供 autogenerate 对比。

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=get_settings().database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = build_engine(get_settings())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
