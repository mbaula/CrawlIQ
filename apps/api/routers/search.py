"""Search across indexed pages."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.session import get_db
from models.domain import CrawlJob, SearchQuery
from schemas.search import SearchResponse, SearchResultItem
from services.search_pages import search_indexed_pages

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search(
    q: Annotated[str, Query(min_length=1, description="Search text (will be tokenized).")],
    db: Session = Depends(get_db),
    job_id: Annotated[int | None, Query(description="If set, only pages from this crawl job.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SearchResponse:
    trimmed_query = q.strip()
    if not trimmed_query:
        raise HTTPException(
            status_code=422,
            detail="Query must contain at least one non-whitespace character.",
        )

    if job_id is not None and db.get(CrawlJob, job_id) is None:
        raise HTTPException(status_code=404, detail="crawl job not found")

    started = time.perf_counter()
    result_rows = search_indexed_pages(
        db,
        raw_query=trimmed_query,
        crawl_job_id=job_id,
        result_limit=limit,
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
