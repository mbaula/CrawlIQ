"""Search across indexed pages."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from db.session import get_db
from models.domain import CrawlJob, SearchQuery
from schemas.search import SearchQueryRead, SearchResponse, SearchResultItem, SearchStatsResponse
from services.search_graph_rerank import search_indexed_pages_graph_enhanced
from services.search_pages import search_indexed_pages
from services.search_related import attach_related_to_search_results

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search(
    q: Annotated[str, Query(min_length=1, description="Search text (will be tokenized).")],
    db: Session = Depends(get_db),
    job_id: Annotated[int | None, Query(description="If set, only pages from this crawl job.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    include_related: Annotated[
        bool,
        Query(description="If true, attach graph neighbors per hit (requires job_id)."),
    ] = False,
    related_limit: Annotated[
        int,
        Query(ge=1, le=10, description="Max related neighbors per hit when include_related is true."),
    ] = 3,
    graph_enhanced: Annotated[
        bool,
        Query(description="If true, rerank with BM25 + graph signals (requires job_id)."),
    ] = False,
) -> SearchResponse:
    trimmed_query = q.strip()
    if not trimmed_query:
        raise HTTPException(
            status_code=422,
            detail="Query must contain at least one non-whitespace character.",
        )

    if include_related and job_id is None:
        raise HTTPException(
            status_code=422,
            detail="job_id is required when include_related is true",
        )

    if graph_enhanced and job_id is None:
        raise HTTPException(
            status_code=422,
            detail="job_id is required when graph_enhanced is true",
        )

    if job_id is not None and db.get(CrawlJob, job_id) is None:
        raise HTTPException(status_code=404, detail="crawl job not found")

    started = time.perf_counter()
    settings = get_settings()
    if graph_enhanced and job_id is not None:
        result_rows = search_indexed_pages_graph_enhanced(
            db,
            raw_query=trimmed_query,
            crawl_job_id=job_id,
            result_limit=limit,
            settings=settings,
        )
    else:
        result_rows = search_indexed_pages(
            db,
            raw_query=trimmed_query,
            crawl_job_id=job_id,
            result_limit=limit,
        )
    for row in result_rows:
        row["related"] = []
    if include_related and job_id is not None:
        attach_related_to_search_results(
            db,
            crawl_job_id=job_id,
            result_rows=result_rows,
            related_limit=related_limit,
        )
    elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))

    results = [SearchResultItem(**row) for row in result_rows]
    result_count = len(results)

    db.add(
        SearchQuery(
            query=trimmed_query,
            result_count=result_count,
            latency_ms=elapsed_ms,
        ),
    )
    db.commit()

    return SearchResponse(
        query=trimmed_query,
        result_count=result_count,
        latency_ms=elapsed_ms,
        results=results,
    )


@router.get("/search/stats", response_model=SearchStatsResponse)
def search_stats(
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchStatsResponse:
    stmt = (
        select(SearchQuery)
        .order_by(SearchQuery.created_at.desc(), SearchQuery.id.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = list(db.scalars(stmt).all())
    recent = [SearchQueryRead.model_validate(r) for r in rows]
    return SearchStatsResponse(recent=recent)
