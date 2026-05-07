"""System stats endpoint for the dashboard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from db.session import get_db
from models.domain import CrawlError, CrawlJob, Page, SearchQuery
from schemas.stats import CrawlStatsRead, DomainCount, SearchQueryRead

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=CrawlStatsRead)
def get_stats(
    db: Session = Depends(get_db),
    recent_search_limit: Annotated[int, Query(ge=1, le=200)] = 25,
    top_domain_limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> CrawlStatsRead:
    jobs_row = db.execute(
        select(
            func.count(CrawlJob.id),
            func.coalesce(func.sum(CrawlJob.pages_crawled), 0),
            func.coalesce(func.sum(CrawlJob.pages_indexed), 0),
            func.coalesce(func.sum(CrawlJob.pages_failed), 0),
        ),
    ).one()
    total_crawl_jobs = int(jobs_row[0] or 0)
    total_pages_crawled = int(jobs_row[1] or 0)
    total_pages_indexed = int(jobs_row[2] or 0)
    total_failures = int(jobs_row[3] or 0)

    failed_url_count = int(
        db.scalar(
            select(func.count(distinct(CrawlError.normalized_url))),
        )
        or 0
    )

    avg_latency = float(
        db.scalar(select(func.coalesce(func.avg(SearchQuery.latency_ms), 0))) or 0,
    )

    recent_rows = list(
        db.scalars(
            select(SearchQuery)
            .order_by(SearchQuery.created_at.desc(), SearchQuery.id.desc())
            .limit(recent_search_limit),
        ).all(),
    )
    recent_searches = [SearchQueryRead.model_validate(r) for r in recent_rows]

    domain_rows = list(
        db.execute(
            select(Page.domain, func.count(Page.id))
            .where(Page.indexed_at.isnot(None))
            .group_by(Page.domain)
            .order_by(func.count(Page.id).desc(), Page.domain.asc())
            .limit(top_domain_limit),
        ).all(),
    )
    top_crawled_domains = [
        DomainCount(domain=str(domain), page_count=int(count)) for domain, count in domain_rows
    ]

    return CrawlStatsRead(
        total_crawl_jobs=total_crawl_jobs,
        total_pages_crawled=total_pages_crawled,
        total_pages_indexed=total_pages_indexed,
        total_failures=total_failures,
        failed_url_count=failed_url_count,
        average_search_latency_ms=avg_latency,
        recent_searches=recent_searches,
        top_crawled_domains=top_crawled_domains,
    )

