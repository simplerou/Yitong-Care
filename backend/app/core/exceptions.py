from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


class BusinessError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


def register_exception_handlers(app: FastAPI):
    @app.exception_handler(BusinessError)
    async def business_error(_request: Request, exc: BusinessError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, exc: SQLAlchemyError):
        if isinstance(exc, IntegrityError):
            return JSONResponse(status_code=409, content={"detail": "数据已变化或存在关联记录，请刷新后重试。"})
        args = getattr(getattr(exc, "orig", None), "args", ())
        code = args[0] if args else None
        detail = "数据库暂不可用，请检查 MySQL 连接后重试。"
        if code in (1146, 1054):
            detail = "数据库结构尚未更新，请在后端执行 alembic upgrade head。"
        return JSONResponse(status_code=503, content={"detail": detail})
