"""Read-only connectivity check: python -m scripts.check_db."""
import sys

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine


def main() -> int:
    try:
        with engine.connect() as connection:
            row = connection.execute(text(
                "SELECT DATABASE() AS database_name, VERSION() AS version, "
                "@@character_set_database AS charset, @@collation_database AS collation, "
                "@@session.time_zone AS timezone"
            )).mappings().one()
            print("MySQL 连接成功")
            for key, value in row.items():
                print(f"{key}: {value}")
            if row["charset"] != "utf8mb4":
                print("数据库字符集不是 utf8mb4，请先修正数据库配置。", file=sys.stderr)
                return 1
    except SQLAlchemyError as exc:
        code = getattr(getattr(exc, "orig", None), "args", (None,))[0]
        hints = {
            1045: "账号或密码错误，或当前账号没有访问权限。",
            1049: "数据库不存在，请先创建数据库。",
            2002: "无法访问 MySQL socket，请检查 MYSQL_UNIX_SOCKET 和服务状态。",
            2003: "无法连接 MySQL，请检查地址、端口和服务状态。",
        }
        print(f"MySQL 连接失败：{hints.get(code, '请检查 backend/.env 和 MySQL 服务。')}（错误码 {code}）", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
