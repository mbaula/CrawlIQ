"""System stats endpoint for the dashboard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from db.session import get_db
from models.domain import CrawlError, CrawlJob, InvertedIndex, Page, SearchQuery, Term
from schemas.stats import (
    CrawlStatsRead,
    DomainCount,
    ErrorTypeCount,
    FailedUrlRead,
    HttpStatusCount,
    LargestPageRead,
    QueryCount,
    SearchQueryRead,
)

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=CrawlStatsRead)
def get_stats(
    db: Session = Depends(get_db),
    recent_search_limit: Annotated[int, Query(ge=1, le=200)] = 25,
    top_domain_limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> CrawlStatsRead:
    # Core job stats
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
        db.scalar(select(func.count(distinct(CrawlError.normalized_url)))) or 0
    )

    # Crawl quality metrics
    total_attempted = total_pages_crawled + total_failures
    crawl_success_rate = total_pages_crawled / total_attempted if total_attempted > 0 else 1.0
    avg_pages_per_job = total_pages_crawled / total_crawl_jobs if total_crawl_jobs > 0 else 0.0

    # Average crawl duration (completed jobs only)
    avg_duration_row = db.execute(
        select(
            func.avg(
                func.extract("epoch", CrawlJob.finished_at) -
                func.extract("epoch", CrawlJob.started_at)
            )
        ).where(
            CrawlJob.started_at.isnot(None),
            CrawlJob.finished_at.isnot(None),
        )
    ).scalar()
    avg_crawl_duration_seconds = float(avg_duration_row) if avg_duration_row else None

    # Index health metrics
    index_coverage = total_pages_indexed / total_pages_crawled if total_pages_crawled > 0 else 1.0
    unique_terms = int(db.scalar(select(func.count(Term.id))) or 0)
    total_postings = int(db.scalar(select(func.count(InvertedIndex.id))) or 0)

    avg_terms_result = db.scalar(
        select(func.avg(Page.token_count)).where(
            Page.indexed_at.isnot(None),
            Page.token_count > 0,
        )
    )
    avg_terms_per_page = float(avg_terms_result) if avg_terms_result else 0.0

    # Largest page by token count
    largest_page_row = db.execute(
        select(Page.id, Page.url, Page.title, Page.token_count)
        .where(Page.indexed_at.isnot(None), Page.token_count > 0)
        .order_by(Page.token_count.desc())
        .limit(1)
    ).first()
    largest_page = (
        LargestPageRead(
            page_id=int(largest_page_row[0]),
            url=str(largest_page_row[1]),
            title=largest_page_row[2],
            token_count=int(largest_page_row[3]),
        )
        if largest_page_row
        else None
    )

    # Last indexed timestamp
    last_indexed_at = db.scalar(
        select(func.max(Page.indexed_at)).where(Page.indexed_at.isnot(None))
    )

    # Search stats
    search_stats_row = db.execute(
        select(
            func.count(SearchQuery.id),
            func.count(SearchQuery.id).filter(SearchQuery.result_count == 0),
            func.coalesce(func.avg(SearchQuery.result_count), 0),
            func.coalesce(func.avg(SearchQuery.latency_ms), 0),
        )
    ).one()
    total_searches = int(search_stats_row[0] or 0)
    zero_result_searches = int(search_stats_row[1] or 0)
    avg_results_per_search = float(search_stats_row[2] or 0)
    average_search_latency_ms = float(search_stats_row[3] or 0)
    zero_result_rate = zero_result_searches / total_searches if total_searches > 0 else 0.0

    # P95 search latency using percentile_cont
    p95_result = db.scalar(
        select(func.percentile_cont(0.95).within_group(SearchQuery.latency_ms))
    )
    p95_search_latency_ms = float(p95_result) if p95_result else 0.0

    # Recent searches
    recent_rows = list(
        db.scalars(
            select(SearchQuery)
            .order_by(SearchQuery.created_at.desc(), SearchQuery.id.desc())
            .limit(recent_search_limit)
        ).all()
    )
    recent_searches = [SearchQueryRead.model_validate(r) for r in recent_rows]

    # Recent zero-result searches
    zero_result_rows = list(
        db.scalars(
            select(SearchQuery)
            .where(SearchQuery.result_count == 0)
            .order_by(SearchQuery.created_at.desc(), SearchQuery.id.desc())
            .limit(10)
        ).all()
    )
    recent_zero_result_searches = [SearchQueryRead.model_validate(r) for r in zero_result_rows]

    # Top queries by frequency
    top_query_rows = list(
        db.execute(
            select(SearchQuery.query, func.count(SearchQuery.id).label("cnt"))
            .group_by(SearchQuery.query)
            .order_by(func.count(SearchQuery.id).desc())
            .limit(10)
        ).all()
    )
    top_queries = [QueryCount(query=str(q), count=int(c)) for q, c in top_query_rows]

    # Top crawled domains
    domain_rows = list(
        db.execute(
            select(Page.domain, func.count(Page.id))
            .where(Page.indexed_at.isnot(None))
            .group_by(Page.domain)
            .order_by(func.count(Page.id).desc(), Page.domain.asc())
            .limit(top_domain_limit)
        ).all()
    )
    top_crawled_domains = [
        DomainCount(domain=str(domain), page_count=int(count))
        for domain, count in domain_rows
    ]

    # Failures by error type
    error_type_rows = list(
        db.execute(
            select(CrawlError.error_type, func.count(CrawlError.id))
            .group_by(CrawlError.error_type)
            .order_by(func.count(CrawlError.id).desc())
        ).all()
    )
    failures_by_type = [
        ErrorTypeCount(error_type=str(et), count=int(c))
        for et, c in error_type_rows
    ]

    # HTTP status distribution
    http_status_rows = list(
        db.execute(
            select(Page.status_code, func.count(Page.id))
            .where(Page.status_code.isnot(None))
            .group_by(Page.status_code)
            .order_by(Page.status_code.asc())
        ).all()
    )
    http_status_distribution = [
        HttpStatusCount(status_code=int(sc), count=int(c))
        for sc, c in http_status_rows
    ]

    # Recent failed URLs
    failed_url_rows = list(
        db.execute(
            select(
                CrawlError.url,
                CrawlError.error_type,
                CrawlError.error_message,
                CrawlError.created_at,
            )
            .order_by(CrawlError.created_at.desc())
            .limit(10)
        ).all()
    )
    recent_failed_urls = [
        FailedUrlRead(url=str(u), error_type=str(et), error_message=em, created_at=ca)
        for u, et, em, ca in failed_url_rows
    ]

    return CrawlStatsRead(
        total_crawl_jobs=total_crawl_jobs,
        total_pages_crawled=total_pages_crawled,
        total_pages_indexed=total_pages_indexed,
        total_failures=total_failures,
        failed_url_count=failed_url_count,
        crawl_success_rate=crawl_success_rate,
        avg_pages_per_job=avg_pages_per_job,
        avg_crawl_duration_seconds=avg_crawl_duration_seconds,
        index_coverage=index_coverage,
        unique_terms=unique_terms,
        total_postings=total_postings,
        avg_terms_per_page=avg_terms_per_page,
        largest_page=largest_page,
        last_indexed_at=last_indexed_at,
        total_searches=total_searches,
        zero_result_searches=zero_result_searches,
        zero_result_rate=zero_result_rate,
        avg_results_per_search=avg_results_per_search,
        average_search_latency_ms=average_search_latency_ms,
        p95_search_latency_ms=p95_search_latency_ms,
        recent_searches=recent_searches,
        recent_zero_result_searches=recent_zero_result_searches,
        top_queries=top_queries,
        top_crawled_domains=top_crawled_domains,
        failures_by_type=failures_by_type,
        http_status_distribution=http_status_distribution,
        recent_failed_urls=recent_failed_urls,
    )

