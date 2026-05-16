"""Response models for ``GET /graph/health`` (thin v1 dashboard)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GraphHealthSummaryRead(BaseModel):
    page_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    metrics_count: int = Field(ge=0)
    cluster_row_count: int = Field(ge=0, description="Rows in ``page_graph_clusters`` for this job.")
    distinct_cluster_ids: int = Field(ge=0, description="Distinct ``cluster_id`` values.")
    orphan_count: int = Field(ge=0)
    duplicate_cluster_count: int = Field(ge=0, description="Canonical pages with outgoing ``near_duplicate`` edges.")
    orphan_detection_warning: str | None = Field(
        default=None,
        description="Set when orphan detection used edge counts instead of metrics.",
    )


class GraphHealthPageRow(BaseModel):
    page_id: int
    title: str | None
    url: str
    pagerank: float | None = None
    in_degree: int | None = None
    out_degree: int | None = None
    link_in_count: int | None = Field(
        default=None,
        description="Incoming ``link`` edges only; present for most-linked rows.",
    )


class GraphHealthClusterRow(BaseModel):
    cluster_id: int
    member_count: int
    representative_page_id: int
    representative_title: str | None
    representative_url: str
    cluster_label: str | None = None
    sample_urls: list[str] = Field(default_factory=list, description="Up to a few member URLs for context.")


class GraphHealthDupNeighborRead(BaseModel):
    page_id: int
    title: str | None
    url: str
    weight: float
    evidence: Any | None = None


class GraphHealthDuplicateClusterRead(BaseModel):
    canonical_page_id: int
    canonical_title: str | None
    canonical_url: str
    duplicate_count: int
    duplicates: list[GraphHealthDupNeighborRead] = Field(
        description="Near-duplicate targets (outgoing ``near_duplicate`` from canonical).",
    )


class GraphHealthRead(BaseModel):
    job_id: int | None = None
    message: str | None = Field(default=None, description="Hint when ``job_id`` was omitted or data is empty.")
    summary: GraphHealthSummaryRead | None = None
    top_pagerank_pages: list[GraphHealthPageRow] = Field(default_factory=list)
    hub_pages: list[GraphHealthPageRow] = Field(default_factory=list)
    authority_pages: list[GraphHealthPageRow] = Field(default_factory=list)
    orphan_pages: list[GraphHealthPageRow] = Field(default_factory=list)
    largest_clusters: list[GraphHealthClusterRow] = Field(default_factory=list)
    small_clusters: list[GraphHealthClusterRow] = Field(default_factory=list)
    duplicate_clusters: list[GraphHealthDuplicateClusterRead] = Field(default_factory=list)
    most_linked_pages: list[GraphHealthPageRow] = Field(
        default_factory=list,
        description="Top pages by count of incoming ``link`` edges.",
    )
