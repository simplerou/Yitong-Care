"""Create the configured database if absent; never overwrite an existing one."""
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings


def main() -> int:
    settings = get_settings()
    engine = create_engine(
        settings.database_url(include_database=False),
        connect_args={"connect_timeout": settings.mysql_connect_timeout},
        hide_parameters=True,
    )
    # 数据库名已在 Settings 限制为字母、数字和下划线，仍按标识符规则引用。
    name = engine.dialect.identifier_preparer.quote_identifier(settings.mysql_database)
    try:
        with engine.connect() as connection:
            connection.execute(text(
                f"CREATE DATABASE IF NOT EXISTS {name} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            ))
        print(f"数据库已就绪：{settings.mysql_database}（已有数据库不作修改）")
    except SQLAlchemyError:
        print("创建数据库失败：请检查连接信息及账号的 CREATE 权限。", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
