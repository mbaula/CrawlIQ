"""Response models for read-only graph APIs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GraphNodeMetricsRead(BaseModel):
    pagerank: float | None = None
    in_degree: int
    out_degree: int
    betweenness: float | None = None
    closeness: float | None = None


class GraphNodeRead(BaseModel):
    page_id: int
    title: str | None
    url: str
    normalized_url: str
    depth: int
    metrics: GraphNodeMetricsRead | None = None
    cluster_id: int | None = None


class GraphEdgeRead(BaseModel):
    edge_id: int
    source_page_id: int
    target_page_id: int
    edge_type: str
    weight: float
    evidence: Any | None = None
    reason: str = Field(description="Human-readable explanation from edge type and stored evidence.")


class GraphSubgraphRead(BaseModel):
    """Bounded neighborhood + induced edges for one crawl job."""

    crawl_job_id: int
    center_page_id: int
    radius: int
    max_nodes: int
    nodes: list[GraphNodeRead]
    edges: list[GraphEdgeRead]


class GraphEdgeTypeCountRead(BaseModel):
    edge_type: str
    count: int


class GraphStatsRead(BaseModel):
    crawl_job_id: int
    page_count: int
    edge_count: int
    edge_counts_by_type: list[GraphEdgeTypeCountRead]
    page_graph_metrics_count: int
    page_graph_cluster_rows: int
    distinct_cluster_ids: int


class GraphClusterRowRead(BaseModel):
    page_id: int
    cluster_id: int
    cluster_label: str | None = None


class GraphClustersRead(BaseModel):
    crawl_job_id: int
    items: list[GraphClusterRowRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)


GraphQueryNodeRole = Literal["query_match", "related_neighbor", "duplicate"]


class GraphQuerySelectedJobRead(BaseModel):
    crawl_job_id: int
    selection_mode: Literal["auto", "explicit"]
    total_bm25_score: float = Field(description="Sum of raw BM25 scores for hits in the selection pool for this job.")
    hit_count: int = Field(ge=0, description="Number of hits in the selection pool for this job.")
    message: str = Field(description="Human-readable summary of how this job was chosen.")


class GraphQueryNodeRead(BaseModel):
    page_id: int
    title: str | None
    url: str
    normalized_url: str
    depth: int
    role: GraphQueryNodeRole
    bm25_score: float | None = Field(
        default=None,
        description="Raw BM25 score for query_match nodes; null for other roles.",
    )
    metrics: GraphNodeMetricsRead | None = None
    cluster_id: int | None = None


class GraphQueryRead(BaseModel):
    """BM25-seeded neighborhood within one crawl job"""

    query: str
    message: str | None = Field(
        default=None,
        description="Set when there are no hits or the graph is empty; null on success.",
    )
    global_hit_limit: int = Field(ge=1, description="Cap on BM25 hits in the selection pool for this request.")
    max_seed_pages: int
    radius: int
    max_nodes: int
    expansion_edge_types: list[str]
    selected_job: GraphQuerySelectedJobRead | None = None
    seed_page_ids: list[int] = Field(default_factory=list)
    nodes: list[GraphQueryNodeRead]
    edges: list[GraphEdgeRead]
