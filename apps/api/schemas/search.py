"""API models for search endpoints."""

from datetime import datetime
from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    """One ranked hit for a search query."""

    page_id: int
    title: str | None
    url: str
    score: float = Field(description="Higher scores are more relevant (relative ranking).")
    snippet: str
    matched_terms: list[str] = Field(
        default_factory=list,
        description="Query terms (after tokenization) that matched this page.",
    )


class SearchResponse(BaseModel):
    """Response for ``GET /search``."""

    query: str
    result_count: int
    latency_ms: int
    results: list[SearchResultItem]


class SearchQueryRead(BaseModel):
    """Row from ``search_queries`` for stats/analytics."""

    model_config = {"from_attributes": True}  # pydantic v2
    query: str
    result_count: int
    latency_ms: int
    created_at: datetime


class SearchStatsResponse(BaseModel):
    """Response for ``GET /search/stats``."""

    recent: list[SearchQueryRead]
