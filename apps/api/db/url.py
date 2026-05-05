"""Normalize SQLAlchemy database URLs for sync drivers (psycopg v3)."""


def sync_engine_url(url: str) -> str:
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url
