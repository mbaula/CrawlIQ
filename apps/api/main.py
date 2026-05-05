from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config import Settings, get_settings
from db.session import get_engine
from routers.crawl_jobs import router as crawl_jobs_router

app = FastAPI(title="CrawlIQ API")
app.include_router(crawl_jobs_router)


@lru_cache
def _cached_settings() -> Settings:
    return get_settings()


def settings_dep() -> Settings:
    return _cached_settings()


@app.get("/health")
def health(settings: Settings = Depends(settings_dep)) -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.get("/ready")
def ready(settings: Settings = Depends(settings_dep)) -> dict[str, str]:
    """Verifies Postgres connectivity (Compose healthcheck can keep using ``/health``)."""
    if not (settings.database_url or "").strip():
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
    try:
        with Session(bind=get_engine()) as session:
            session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=503, detail=f"database: {exc}") from exc
    return {"database": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "CrawlIQ API"}
