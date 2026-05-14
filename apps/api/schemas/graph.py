"""Response models for read-only graph APIs."""

from __future__ import annotations

from typing import Any

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
