"""API models for system stats endpoint."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DomainCount(BaseModel):
    domain: str
    page_count: int = Field(ge=0)


class CrawlStatsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_crawl_jobs: int = Field(ge=0)
    total_pages_crawled: int = Field(ge=0)
    total_pages_indexed: int = Field(ge=0)
    total_failures: int = Field(ge=0)
    failed_url_count: int = Field(ge=0)

    average_search_latency_ms: float = Field(ge=0)
    recent_searches: list["SearchQueryRead"] = Field(default_factory=list)

    top_crawled_domains: list[DomainCount] = Field(default_factory=list)


class SearchQueryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    query: str
    result_count: int
    latency_ms: int
    created_at: datetime

