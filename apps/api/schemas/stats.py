"""API models for system stats endpoint."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DomainCount(BaseModel):
    domain: str
    page_count: int = Field(ge=0)


class DomainFailureCount(BaseModel):
    """Crawl errors aggregated by host extracted from error URL."""

    domain: str
    failure_count: int = Field(ge=0)


class ErrorTypeCount(BaseModel):
    error_type: str
    count: int = Field(ge=0)


class HttpStatusCount(BaseModel):
    status_code: int
    count: int = Field(ge=0)


class HttpStatusClassTotals(BaseModel):
    """Rollup of combined HTTP status distribution into status classes."""

    status_2xx: int = Field(ge=0)
    status_3xx: int = Field(ge=0)
    status_4xx: int = Field(ge=0)
    status_5xx: int = Field(ge=0)


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
    """Crawl/index/search/reliability metrics (Issue 44: clear outcome definitions)."""

    model_config = ConfigDict(from_attributes=True)

    # Canonical outcome counts (DB-derived where possible)
    total_urls_attempted: int = Field(
        ge=0,
        description="Page rows plus crawl error rows (each represents one URL attempt outcome).",
    )
    total_pages_crawled: int = Field(
        ge=0,
        description="Rows in ``pages`` (successful fetches). Prefer this over summing job counters.",
    )
    total_pages_indexed: int = Field(ge=0)
    pages_pending_indexing: int = Field(
        ge=0,
        description="Fetched but not yet indexed (indexed_at IS NULL).",
    )
    skipped_urls_count: int = Field(
        ge=0,
        description="Policy skips with no full fetch (e.g. robots_disallow).",
    )
    policy_rejected_urls_count: int = Field(
        ge=0,
        description="HTTP response rejected as not indexable (not_indexable, oversized).",
    )
    total_skipped_rows: int = Field(
        ge=0,
        description="Skipped + policy-rejected crawl_error rows (robots, not_indexable, oversized).",
    )
    fetch_failure_row_count: int = Field(
        ge=0,
        description="crawl_errors that are true fetch/post-fetch failures (excludes policy skips).",
    )

    total_crawl_jobs: int = Field(ge=0)
    total_failures: int = Field(ge=0, description="Rows in ``crawl_errors``.")
    failed_url_count: int = Field(ge=0, description="Distinct normalized URLs in ``crawl_errors``.")

    # Crawl quality
    crawl_success_rate: float = Field(ge=0, le=1)
    avg_pages_per_job: float = Field(ge=0)
    avg_crawl_duration_seconds: float | None = Field(default=None)

    # Index health
    index_coverage: float = Field(ge=0, le=1)
    unique_terms: int = Field(ge=0)
    total_postings: int = Field(ge=0)
    avg_terms_per_page: float = Field(ge=0)
    median_terms_per_page: float = Field(ge=0)
    p95_terms_per_page: float = Field(ge=0)
    largest_page: LargestPageRead | None = Field(default=None)
    last_indexed_at: datetime | None = Field(default=None)

    # Fetch latency (pages with fetch_duration_ms populated)
    avg_fetch_latency_ms: float | None = Field(
        default=None,
        description="Mean HTTP fetch time for successful pages; null if no samples.",
    )
    p95_fetch_latency_ms: float | None = Field(default=None)

    # Search stats
    total_searches: int = Field(ge=0)
    zero_result_searches: int = Field(ge=0)
    zero_result_rate: float = Field(ge=0, le=1)
    avg_results_per_search: float = Field(ge=0)
    searches_hitting_result_cap: int = Field(
        ge=0,
        description="Queries with result_count >= 20 (default search cap).",
    )
    average_search_latency_ms: float = Field(ge=0)
    p95_search_latency_ms: float = Field(ge=0)
    slowest_search_latency_ms: int | None = Field(default=None)
    slowest_search_query: str | None = Field(default=None)

    # Lists
    recent_searches: list["SearchQueryRead"] = Field(default_factory=list)
    recent_zero_result_searches: list["SearchQueryRead"] = Field(default_factory=list)
    top_queries: list[QueryCount] = Field(default_factory=list)
    top_crawled_domains: list[DomainCount] = Field(default_factory=list)

    # Failure breakdown (Issue 45: skipped vs fetch failures)
    skipped_breakdown: list[ErrorTypeCount] = Field(
        default_factory=list,
        description="Policy / intentional skips with readable labels.",
    )
    fetch_failures_breakdown: list[ErrorTypeCount] = Field(
        default_factory=list,
        description="Transport and post-fetch failures; HTTP 429 split out from other http_error.",
    )
    failures_by_type: list[ErrorTypeCount] = Field(
        default_factory=list,
        description="Raw error_type counts (all crawl_errors).",
    )
    http_status_distribution: list[HttpStatusCount] = Field(
        default_factory=list,
        description="Combined successful page status codes + failed fetch HTTP codes.",
    )
    http_status_class_totals: HttpStatusClassTotals = Field(
        default_factory=lambda: HttpStatusClassTotals(),
    )
    recent_failed_urls: list[FailedUrlRead] = Field(default_factory=list)

    # Reliability
    rate_limited_url_count: int = Field(ge=0, description="Crawl errors with HTTP 429.")
    timeout_fetch_count: int = Field(ge=0, description="Crawl errors with error_type=timeout.")
    top_failure_domains: list[DomainFailureCount] = Field(default_factory=list)


class SearchQueryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    query: str
    result_count: int
    latency_ms: int
    created_at: datetime
