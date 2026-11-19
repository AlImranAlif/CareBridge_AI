import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.db.session import get_database_engine

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger("carebridge.health")


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Service is not ready")
    engine = None
    try:
        engine = get_database_engine(settings.database_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("database_readiness_failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Service is not ready") from None
    return {"status": "ready"}
