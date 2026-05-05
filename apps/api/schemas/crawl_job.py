from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CrawlJobRead(BaseModel):
    """Full job row for GET list/detail."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    seed_url: str
    normalized_seed_url: str
    status: str
    max_pages: int
    max_depth: int
    same_domain_only: bool
    pages_crawled: int
    pages_indexed: int
    pages_failed: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None


class PageRead(BaseModel):
    """Crawled page row (no ``extracted_text`` — can be very large)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    crawl_job_id: int
    url: str
    normalized_url: str
    domain: str
    title: str | None
    raw_html_hash: str | None
    content_hash: str | None
    status_code: int | None
    depth: int
    fetched_at: datetime | None
    indexed_at: datetime | None
    created_at: datetime


class CrawlErrorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    crawl_job_id: int
    url: str
    normalized_url: str
    error_type: str
    error_message: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime


class CrawlJobCreateRequest(BaseModel):
    seed_url: HttpUrl
    max_pages: int = Field(ge=1, le=10_000)
    max_depth: int = Field(ge=0, le=10)
    same_domain_only: bool = True


class CrawlJobCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seed_url: str
    status: str
    max_pages: int
    max_depth: int
    same_domain_only: bool
    created_at: datetime
