"""API models for system stats endpoint."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DomainCount(BaseModel):
    domain: str
    page_count: int = Field(ge=0)


class ErrorTypeCount(BaseModel):
    error_type: str
    count: int = Field(ge=0)


class HttpStatusCount(BaseModel):
    status_code: int
    count: int = Field(ge=0)


class QueryCount(BaseModel):
    query: str
    count: int = Field(ge=0)


class FailedUrlRead(BaseModel):
    url: str
    error_type: str
    error_message: str | None
    created_at: datetime


class LargestPageRead(BaseModel):
    page_id: int
    url: str
    title: str | None
    token_count: int


class CrawlStatsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # Core counts
    total_crawl_jobs: int = Field(ge=0)
    total_pages_crawled: int = Field(ge=0)
    total_pages_indexed: int = Field(ge=0)
    total_failures: int = Field(ge=0)
    failed_url_count: int = Field(ge=0)

    # Crawl quality
    crawl_success_rate: float = Field(ge=0, le=1)
    avg_pages_per_job: float = Field(ge=0)
    avg_crawl_duration_seconds: float | None = Field(default=None)

    # Index health
    index_coverage: float = Field(ge=0, le=1)
    unique_terms: int = Field(ge=0)
    total_postings: int = Field(ge=0)
    avg_terms_per_page: float = Field(ge=0)
    largest_page: LargestPageRead | None = Field(default=None)
    last_indexed_at: datetime | None = Field(default=None)

    # Search stats
    total_searches: int = Field(ge=0)
    zero_result_searches: int = Field(ge=0)
    zero_result_rate: float = Field(ge=0, le=1)
    avg_results_per_search: float = Field(ge=0)
    average_search_latency_ms: float = Field(ge=0)
    p95_search_latency_ms: float = Field(ge=0)

    # Lists
    recent_searches: list["SearchQueryRead"] = Field(default_factory=list)
    recent_zero_result_searches: list["SearchQueryRead"] = Field(default_factory=list)
    top_queries: list[QueryCount] = Field(default_factory=list)
    top_crawled_domains: list[DomainCount] = Field(default_factory=list)

    # Failure breakdown
    failures_by_type: list[ErrorTypeCount] = Field(default_factory=list)
    http_status_distribution: list[HttpStatusCount] = Field(default_factory=list)
    recent_failed_urls: list[FailedUrlRead] = Field(default_factory=list)


class SearchQueryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    query: str
    result_count: int
    latency_ms: int
    created_at: datetime

