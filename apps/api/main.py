from functools import lru_cache

from fastapi import Depends, FastAPI

from config import Settings, get_settings

app = FastAPI(title="CrawlIQ API")


@lru_cache
def _cached_settings() -> Settings:
    return get_settings()


def settings_dep() -> Settings:
    return _cached_settings()


@app.get("/health")
def health(settings: Settings = Depends(settings_dep)) -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "CrawlIQ API"}
