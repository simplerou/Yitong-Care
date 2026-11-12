from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import create_api_router
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.session import engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    engine.dispose()


def create_app(*, legacy_compatibility: bool = False) -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="禾龄通 API", version="0.1.0", lifespan=lifespan)
    application.state.legacy_compatibility=legacy_compatibility
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    application.include_router(health_router, prefix="/api")
    application.include_router(auth_router)
    from app.api.v1.account_reviews import router as reviews_router
    application.include_router(reviews_router)
    application.include_router(create_api_router(legacy_compatibility=legacy_compatibility))
    register_exception_handlers(application)
    return application


app = create_app()
