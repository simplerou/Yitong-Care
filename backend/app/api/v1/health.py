import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.deps import DatabaseSession

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


@router.get("")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "yitong-care-backend"}


@router.get("/db", response_model=None)
def database_health(db: DatabaseSession):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # 不把连接串、用户名、SQL 参数和底层异常内容返回给客户端。
        logger.warning("MySQL health check failed: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "mysql"})
    return {"status": "ok", "database": "mysql"}
