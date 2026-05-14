"""Read-only graph endpoints (Issue 52)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.session import get_db
from schemas.graph import GraphClustersRead, GraphStatsRead, GraphSubgraphRead
from services.page_graph_read import (
    build_clusters_read,
    build_graph_stats_read,
    build_subgraph_read,
    crawl_job_exists,
    get_page_in_job,
)

router = APIRouter(tags=["graph"])


def _require_crawl_job(session, job_id: int) -> None:
    if not crawl_job_exists(session, job_id):
        raise HTTPException(status_code=404, detail="crawl job not found")


def _require_page_in_job(session, job_id: int, page_id: int) -> None:
    if get_page_in_job(session, job_id, page_id) is None:
        raise HTTPException(status_code=404, detail="page not found")


@router.get("/graph/subgraph", response_model=GraphSubgraphRead)
def get_graph_subgraph(
    job_id: Annotated[int, Query(ge=1, description="Crawl job id.")],
    page_id: Annotated[int, Query(ge=1, description="Center page id.")],
    radius: Annotated[
        int,
        Query(ge=0, le=50, description="Maximum hop distance from the center page (undirected BFS)."),
    ] = 1,
    max_nodes: Annotated[
        int,
        Query(ge=1, le=500, description="Maximum number of pages in the returned node set."),
    ] = 50,
    db: Session = Depends(get_db),
) -> GraphSubgraphRead:
    _require_crawl_job(db, job_id)
    _require_page_in_job(db, job_id, page_id)
    return build_subgraph_read(
        db,
        crawl_job_id=job_id,
        center_page_id=page_id,
        radius=radius,
        max_nodes=max_nodes,
    )


@router.get("/pages/{page_id}/neighbors", response_model=GraphSubgraphRead)
def get_page_neighbors(
    page_id: int,
    job_id: Annotated[int, Query(ge=1, description="Crawl job id.")],
    max_nodes: Annotated[
        int,
        Query(ge=1, le=500, description="Maximum number of pages in the returned node set."),
    ] = 50,
    db: Session = Depends(get_db),
) -> GraphSubgraphRead:
    _require_crawl_job(db, job_id)
    _require_page_in_job(db, job_id, page_id)
    return build_subgraph_read(
        db,
        crawl_job_id=job_id,
        center_page_id=page_id,
        radius=1,
        max_nodes=max_nodes,
    )


@router.get("/pages/{page_id}/graph", response_model=GraphSubgraphRead)
def get_page_graph(
    page_id: int,
    job_id: Annotated[int, Query(ge=1, description="Crawl job id.")],
    radius: Annotated[
        int,
        Query(ge=0, le=50, description="Maximum hop distance from the center page (undirected BFS)."),
    ] = 1,
    max_nodes: Annotated[
        int,
        Query(ge=1, le=500, description="Maximum number of pages in the returned node set."),
    ] = 50,
    db: Session = Depends(get_db),
) -> GraphSubgraphRead:
    _require_crawl_job(db, job_id)
    _require_page_in_job(db, job_id, page_id)
    return build_subgraph_read(
        db,
        crawl_job_id=job_id,
        center_page_id=page_id,
        radius=radius,
        max_nodes=max_nodes,
    )


@router.get("/graph/stats", response_model=GraphStatsRead)
def get_graph_stats(
    job_id: Annotated[int, Query(ge=1, description="Crawl job id.")],
    db: Session = Depends(get_db),
) -> GraphStatsRead:
    _require_crawl_job(db, job_id)
    return build_graph_stats_read(db, crawl_job_id=job_id)


@router.get("/graph/clusters", response_model=GraphClustersRead)
def get_graph_clusters(
    job_id: Annotated[int, Query(ge=1, description="Crawl job id.")],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> GraphClustersRead:
    _require_crawl_job(db, job_id)
    return build_clusters_read(db, crawl_job_id=job_id, limit=limit, offset=offset)
