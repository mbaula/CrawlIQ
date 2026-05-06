"""Engine and request-scoped session for FastAPI."""

from collections.abc import Generator
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings
from db.url import sync_engine_url

_engine = None
_session_factory: Optional[sessionmaker[Session]] = None


def _ensure_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        return
    settings = get_settings()
    url = (settings.database_url or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Configure it to use the database (see .env.example)."
        )
    _engine = create_engine(
        sync_engine_url(url),
        pool_pre_ping=True,
    )
    _session_factory = sessionmaker(
        bind=_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_engine():
    """Return the process-wide sync engine (lazy-initialized)."""
    _ensure_engine()
    assert _engine is not None
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide ``sessionmaker`` (lazy-initialized)."""
    _ensure_engine()
    assert _session_factory is not None
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request (call ``commit()`` in routes after writes)."""
    _ensure_engine()
    assert _session_factory is not None
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()
