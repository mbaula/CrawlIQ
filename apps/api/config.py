"""Load settings from environment (and optional `.env` for local dev)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Monorepo layout: repo-root `.env` (``CrawlIQ/.env``) and optional ``apps/api/.env``.
# Later files override earlier. ``config.py`` lives in ``apps/api/``, so repo root is
# two levels up.
_API_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _API_DIR.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            _REPO_ROOT / ".env",
            _API_DIR / ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "crawliq-api"

    database_url: str = ""
    redis_url: str = ""

    crawl_default_max_pages: int = 100
    crawl_default_max_depth: int = 2
    crawl_request_timeout_seconds: int = 10
    crawl_domain_delay_seconds: int = 1


def get_settings() -> Settings:
    return Settings()
