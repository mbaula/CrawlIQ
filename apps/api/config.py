"""Load settings from environment (and optional `.env` for local dev)."""

from pathlib import Path

from pydantic import Field, model_validator
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
    # RQ kills jobs that exceed their timeout. Default timeout is 1 hour for large crawls
    # (300 pages * 1s delay = 5 min minimum, plus fetch/parse/index time).
    crawl_job_timeout_seconds: int = Field(default=3600, ge=1, le=86_400)
    crawl_domain_delay_seconds: int = 1
    # Empty string → built-in default in ``fetch_html`` (see ``DEFAULT_HTTP_USER_AGENT``).
    crawl_http_user_agent: str = ""
    crawl_max_redirects: int = Field(default=10, ge=1, le=50)
    crawl_max_response_bytes: int = Field(default=5_242_880, ge=1, le=50_000_000)  # ~5 MiB default

    graph_similarity_top_k: int = Field(default=10, ge=1, le=500)
    graph_similarity_min_score: float = Field(default=0.15, ge=0.0, le=1.0)
    graph_near_duplicate_min_score: float = Field(default=0.92, ge=0.0, le=1.0)
    graph_rerank_seed_limit: int = Field(
        default=15,
        ge=3,
        le=200,
        description="Top BM25 pages used as seeds for graph neighbor boost in graph-enhanced search.",
    )
    graph_rerank_max_candidates: int = Field(
        default=200,
        ge=30,
        le=2000,
        description="Max BM25 pages ∪ 1-hop neighbors considered before reranking.",
    )

    @model_validator(mode="after")
    def _graph_rerank_seed_vs_max(self) -> "Settings":
        if self.graph_rerank_seed_limit > self.graph_rerank_max_candidates:
            raise ValueError(
                "graph_rerank_seed_limit must be <= graph_rerank_max_candidates",
            )
        return self


def get_settings() -> Settings:
    return Settings()
