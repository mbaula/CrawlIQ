"""Result of persisting a single crawled page."""

from typing import Literal

from pydantic import BaseModel, Field


class CrawlFrontierSummary(BaseModel):
    """Outcome of ``run_crawl_frontier`` for a crawl job."""

    status: Literal["completed", "failed"]
    error_message: str | None = None


class CrawlPersistResult(BaseModel):
    """Outcome of ``crawl_and_persist_page`` for frontier and metrics."""

    status: Literal["saved", "duplicate", "failed"]
    normalized_url: str = Field(description="Canonical page URL for this attempt")
    page_id: int | None = None
    links_saved: int = Field(0, description="New ``page_links`` rows inserted")
    error_type: str | None = None
    error_message: str | None = None
