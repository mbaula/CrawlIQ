from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CrawlJobRead(BaseModel):
    """Job row for GET list (no extra aggregates)."""

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


class CrawlJobListRead(BaseModel):
    """Paginated list for ``GET /crawl-jobs``."""

    items: list[CrawlJobRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class CrawlJobDetailRead(CrawlJobRead):
    """GET ``/crawl-jobs/{id}``: adds dashboard-oriented progress fields."""

    pages_discovered: int = Field(
        0,
        description="Distinct crawl-eligible link targets seen in parsed HTML for this job.",
    )
    crawl_progress: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="``pages_crawled / max_pages``, capped at 1.",
    )


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
    enqueued: bool = True


class CrawlJobBulkCreateRequest(BaseModel):
    seed_urls: list[HttpUrl] = Field(min_length=1, max_length=500)
    max_pages: int = Field(ge=1, le=10_000)
    max_depth: int = Field(ge=0, le=10)
    same_domain_only: bool = True


class CrawlJobBulkCreateItem(BaseModel):
    seed_url: str
    ok: bool
    job: CrawlJobCreateResponse | None = None
    error: str | None = None


class CrawlJobBulkCreateResponse(BaseModel):
    results: list[CrawlJobBulkCreateItem]


class CrawlJobRetryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    enqueued: bool = True


class CrawlJobLinkEdgesGenerateResponse(BaseModel):
    """Result of ``POST /crawl-jobs/{id}/graph/link-edges``."""

    edges_inserted: int = Field(
        ge=0,
        description="Rows inserted this run (excludes conflicts from prior runs).",
    )


class CrawlJobUrlHierarchyEdgesGenerateResponse(BaseModel):
    """Result of ``POST /crawl-jobs/{id}/graph/url-hierarchy-edges``."""

    edges_inserted: int = Field(
        ge=0,
        description="Rows inserted this run (excludes conflicts from prior runs).",
    )


class CrawlJobContentSimilarityEdgesGenerateResponse(BaseModel):
    """Result of ``POST /crawl-jobs/{id}/graph/content-similarity-edges``."""

    edges_inserted: int = Field(
        ge=0,
        description="Rows inserted this run (excludes conflicts from prior runs).",
    )


class CrawlJobNearDuplicateEdgesGenerateResponse(BaseModel):
    """Result of ``POST /crawl-jobs/{id}/graph/near-duplicate-edges``."""

    edges_inserted: int = Field(
        ge=0,
        description="Rows inserted this run (excludes conflicts from prior runs).",
    )


class CrawlJobGraphMetricsComputeResponse(BaseModel):
    """Result of ``POST /crawl-jobs/{id}/graph/compute-metrics``."""

    pages_count: int = Field(ge=0)
    edges_used: int = Field(ge=0)
    pagerank_iterations: int = Field(ge=0)
    weak_components_count: int = Field(ge=0)
    betweenness_computed: bool
