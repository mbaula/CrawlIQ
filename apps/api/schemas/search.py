"""API models for search endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class RelatedPageRead(BaseModel):
    """Graph neighbor of a search hit (same ``crawl_job_id`` as the search)."""

    page_id: int
    title: str | None
    url: str
    edge_type: str
    strength: float = Field(description="Edge weight (e.g. cosine for content similarity).")
    reason: str = Field(description="Short explanation from edge type and stored evidence.")
    also_related_by: list[str] = Field(
        default_factory=list,
        description="Other edge types between the same hit and neighbor (primary edge chosen by type priority).",
    )


class GraphScoreComponentsRead(BaseModel):
    """Breakdown for graph-enhanced reranked search scores."""

    bm25_raw: float
    bm25_norm: float
    pagerank_norm: float
    neighbor_boost_raw: float
    neighbor_boost_norm: float
    duplicate_penalty_raw: float
    duplicate_penalty_norm: float
    final_score: float


class SearchResultItem(BaseModel):
    """One ranked hit for a search query."""

    page_id: int
    title: str | None
    url: str
    score: float = Field(description="BM25 score, or final rerank score when graph_enhanced is true.")
    snippet: str
    matched_terms: list[str] = Field(
        default_factory=list,
        description="Query terms (after tokenization) that matched this page.",
    )
    related: list[RelatedPageRead] = Field(
        default_factory=list,
        description="Optional graph neighbors when ``include_related`` was requested with ``job_id``.",
    )
    score_components: GraphScoreComponentsRead | None = Field(
        default=None,
        description="Present when ``graph_enhanced`` was used with ``job_id``.",
    )
    score_explanation: str | None = Field(
        default=None,
        description="Human-readable score breakdown for graph-enhanced search.",
    )
    is_duplicate_variant: bool = Field(
        default=False,
        description="True when this hit is a near-duplicate of an earlier hit (annotate_duplicate_hits).",
    )
    canonical_page_id: int | None = Field(
        default=None,
        description="Earlier hit page id when ``is_duplicate_variant`` is true.",
    )
    duplicate_explanation: str | None = Field(
        default=None,
        description="Short note for duplicate variants when annotation is enabled.",
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


class SearchQueryLogResetResponse(BaseModel):
    """Response for ``POST /search/stats/reset``."""

    deleted: int = Field(ge=0, description="Number of ``search_queries`` rows removed.")
