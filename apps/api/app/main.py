from contextlib import asynccontextmanager
from logging import getLogger

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.documents import router as documents_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = getLogger("carebridge.startup")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("application_started environment=%s", settings.app_env)
    yield
    logger.info("application_stopped")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)
install_error_handlers(app)
app.include_router(health_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def service_info() -> dict[str, str]:
    return {"service": settings.app_name, "health": "/api/v1/health/live", "docs": "/docs"}
