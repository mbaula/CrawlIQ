"""System stats endpoint for the dashboard (Issue 44: outcomes, HTTP mix, percentiles)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from db.session import get_db
from models.domain import CrawlError, CrawlJob, InvertedIndex, Page, SearchQuery, Term
from schemas.stats import (
    CrawlStatsRead,
    DomainCount,
    DomainFailureCount,
    ErrorTypeCount,
    FailedUrlRead,
    HttpStatusClassTotals,
    HttpStatusCount,
    LargestPageRead,
    QueryCount,
    SearchQueryRead,
)

router = APIRouter(tags=["stats"])

_SKIPPED_TYPES = frozenset({"robots_disallow"})
_POLICY_REJECT_TYPES = frozenset({"not_indexable", "oversized"})


def _http_class_totals(rows: list[tuple[int, int]]) -> HttpStatusClassTotals:
    two = three = four = five = 0
    for sc, c in rows:
        if 200 <= sc < 300:
            two += int(c)
        elif 300 <= sc < 400:
            three += int(c)
        elif 400 <= sc < 500:
            four += int(c)
        elif 500 <= sc < 600:
            five += int(c)
    return HttpStatusClassTotals(
        status_2xx=two, status_3xx=three, status_4xx=four, status_5xx=five,
    )


_SKIPPED_BREAKDOWN_TYPES = (
    ("robots_disallow", "Robots.txt disallow"),
    ("not_indexable", "Not indexable (MIME / not page-like)"),
    ("oversized", "Oversized response"),
    ("duplicate", "Duplicate URL (same job — not stored as error today)"),
    ("off_domain", "Off-domain (not scheduled — not stored as error today)"),
)


def _skipped_and_fetch_breakdowns(
    db: Session,
    *,
    rate_limited_count: int,
) -> tuple[list[ErrorTypeCount], list[ErrorTypeCount]]:
    """Issue 45: policy skips vs true fetch failures (HTTP 429 split from http_error)."""
    skipped: list[ErrorTypeCount] = []
    for key, label in _SKIPPED_BREAKDOWN_TYPES:
        c = int(
            db.scalar(
                select(func.count(CrawlError.id)).where(CrawlError.error_type == key),
            )
            or 0,
        )
        skipped.append(ErrorTypeCount(error_type=label, count=c))

    policy_types = {"robots_disallow", "not_indexable", "oversized"}
    fetch_rows_raw = list(
        db.execute(
            select(CrawlError.error_type, func.count(CrawlError.id))
            .where(CrawlError.error_type.not_in(policy_types))
            .group_by(CrawlError.error_type)
            .order_by(CrawlError.error_type.asc()),
        ).all(),
    )
    by_fetch: dict[str, int] = {str(et): int(c) for et, c in fetch_rows_raw}

    http_total = int(by_fetch.pop("http_error", 0))
    http_non_rl = max(0, http_total - rate_limited_count)

    fetch_fixed_order = [
        "timeout",
        "connect",
        "tls",
        "protocol",
        "redirect_error",
        "invalid_url",
        "parse_error",
    ]
    fetch_out: list[ErrorTypeCount] = [
        ErrorTypeCount(error_type="HTTP 429 (rate limited)", count=rate_limited_count),
        ErrorTypeCount(error_type="HTTP error (other status)", count=http_non_rl),
    ]
    for key in fetch_fixed_order:
        cnt = int(by_fetch.pop(key, 0))
        fetch_out.append(ErrorTypeCount(error_type=key, count=cnt))
    for k, v in sorted(by_fetch.items(), key=lambda kv: (-kv[1], kv[0])):
        if v:
            fetch_out.append(ErrorTypeCount(error_type=k, count=int(v)))

    return skipped, fetch_out


@router.get("/stats", response_model=CrawlStatsRead)
def get_stats(
    db: Session = Depends(get_db),
    recent_search_limit: Annotated[int, Query(ge=1, le=200)] = 25,
    top_domain_limit: Annotated[int, Query(ge=1, le=50)] = 10,
    top_failure_domain_limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> CrawlStatsRead:
    total_pages_crawled = int(db.scalar(select(func.count(Page.id))) or 0)
    total_pages_indexed = int(
        db.scalar(
            select(func.count(Page.id)).where(Page.indexed_at.isnot(None)),
        )
        or 0
    )
    pages_pending_indexing = int(
        db.scalar(
            select(func.count(Page.id)).where(
                Page.fetched_at.is_not(None),
                Page.indexed_at.is_(None),
            ),
        )
        or 0
    )
    total_crawl_errors = int(db.scalar(select(func.count(CrawlError.id))) or 0)
    total_urls_attempted = total_pages_crawled + total_crawl_errors

    skipped_urls_count = int(
        db.scalar(
            select(func.count(CrawlError.id)).where(CrawlError.error_type.in_(_SKIPPED_TYPES)),
        )
        or 0
    )
    policy_rejected_urls_count = int(
        db.scalar(
            select(func.count(CrawlError.id)).where(CrawlError.error_type.in_(_POLICY_REJECT_TYPES)),
        )
        or 0
    )

    failed_url_count = int(
        db.scalar(select(func.count(func.distinct(CrawlError.normalized_url)))) or 0
    )

    # Job table (durations, job count)
    jobs_row = db.execute(select(func.count(CrawlJob.id))).one()
    total_crawl_jobs = int(jobs_row[0] or 0)

    crawl_success_rate = (
        total_pages_crawled / total_urls_attempted if total_urls_attempted > 0 else 1.0
    )
    avg_pages_per_job = total_pages_crawled / total_crawl_jobs if total_crawl_jobs > 0 else 0.0

    avg_duration_row = db.execute(
        select(
            func.avg(
                func.extract("epoch", CrawlJob.finished_at)
                - func.extract("epoch", CrawlJob.started_at),
            ),
        ).where(
            CrawlJob.started_at.isnot(None),
            CrawlJob.finished_at.isnot(None),
        ),
    ).scalar()
    avg_crawl_duration_seconds = float(avg_duration_row) if avg_duration_row else None

    index_coverage = (
        total_pages_indexed / total_pages_crawled if total_pages_crawled > 0 else 1.0
    )
    unique_terms = int(db.scalar(select(func.count(Term.id))) or 0)
    total_postings = int(db.scalar(select(func.count(InvertedIndex.id))) or 0)

    avg_terms_result = db.scalar(
        select(func.avg(Page.token_count)).where(
            Page.indexed_at.isnot(None),
            Page.token_count > 0,
        ),
    )
    avg_terms_per_page = float(avg_terms_result) if avg_terms_result else 0.0

    median_terms = db.scalar(
        select(func.percentile_cont(0.5).within_group(Page.token_count)).where(
            Page.indexed_at.isnot(None),
            Page.token_count > 0,
        ),
    )
    median_terms_per_page = float(median_terms) if median_terms is not None else 0.0

    p95_terms = db.scalar(
        select(func.percentile_cont(0.95).within_group(Page.token_count)).where(
            Page.indexed_at.isnot(None),
            Page.token_count > 0,
        ),
    )
    p95_terms_per_page = float(p95_terms) if p95_terms is not None else 0.0

    largest_page_row = db.execute(
        select(Page.id, Page.url, Page.title, Page.token_count)
        .where(Page.indexed_at.isnot(None), Page.token_count > 0)
        .order_by(Page.token_count.desc())
        .limit(1),
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

    last_indexed_at = db.scalar(
        select(func.max(Page.indexed_at)).where(Page.indexed_at.isnot(None)),
    )

    avg_fetch = db.scalar(
        select(func.avg(Page.fetch_duration_ms)).where(Page.fetch_duration_ms.isnot(None)),
    )
    p95_fetch = db.scalar(
        select(func.percentile_cont(0.95).within_group(Page.fetch_duration_ms)).where(
            Page.fetch_duration_ms.isnot(None),
        ),
    )
    avg_fetch_latency_ms = float(avg_fetch) if avg_fetch is not None else None
    p95_fetch_latency_ms = float(p95_fetch) if p95_fetch is not None else None

    search_stats_row = db.execute(
        select(
            func.count(SearchQuery.id),
            func.count(SearchQuery.id).filter(SearchQuery.result_count == 0),
            func.coalesce(func.avg(SearchQuery.result_count), 0),
            func.coalesce(func.avg(SearchQuery.latency_ms), 0),
        ),
    ).one()
    total_searches = int(search_stats_row[0] or 0)
    zero_result_searches = int(search_stats_row[1] or 0)
    avg_results_per_search = float(search_stats_row[2] or 0)
    average_search_latency_ms = float(search_stats_row[3] or 0)
    zero_result_rate = zero_result_searches / total_searches if total_searches > 0 else 0.0

    searches_hitting_result_cap = int(
        db.scalar(select(func.count(SearchQuery.id)).where(SearchQuery.result_count >= 20)) or 0,
    )

    p95_result = db.scalar(
        select(func.percentile_cont(0.95).within_group(SearchQuery.latency_ms)),
    )
    p95_search_latency_ms = float(p95_result) if p95_result else 0.0

    slow_row = db.execute(
        select(SearchQuery.query, SearchQuery.latency_ms).order_by(
            SearchQuery.latency_ms.desc(), SearchQuery.id.desc(),
        ).limit(1),
    ).first()
    slowest_search_query = str(slow_row[0]) if slow_row else None
    slowest_search_latency_ms = int(slow_row[1]) if slow_row else None

    recent_rows = list(
        db.scalars(
            select(SearchQuery)
            .order_by(SearchQuery.created_at.desc(), SearchQuery.id.desc())
            .limit(recent_search_limit),
        ).all(),
    )
    recent_searches = [SearchQueryRead.model_validate(r) for r in recent_rows]

    zero_result_rows = list(
        db.scalars(
            select(SearchQuery)
            .where(SearchQuery.result_count == 0)
            .order_by(SearchQuery.created_at.desc(), SearchQuery.id.desc())
            .limit(10),
        ).all(),
    )
    recent_zero_result_searches = [SearchQueryRead.model_validate(r) for r in zero_result_rows]

    top_query_rows = list(
        db.execute(
            select(SearchQuery.query, func.count(SearchQuery.id).label("cnt"))
            .group_by(SearchQuery.query)
            .order_by(func.count(SearchQuery.id).desc())
            .limit(10),
        ).all(),
    )
    top_queries = [QueryCount(query=str(q), count=int(c)) for q, c in top_query_rows]

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

    error_type_rows = list(
        db.execute(
            select(CrawlError.error_type, func.count(CrawlError.id))
            .group_by(CrawlError.error_type)
            .order_by(func.count(CrawlError.id).desc()),
        ).all(),
    )
    failures_by_type = [
        ErrorTypeCount(error_type=str(et), count=int(c)) for et, c in error_type_rows
    ]

    rate_limited_url_count = int(
        db.scalar(
            select(func.count(CrawlError.id)).where(CrawlError.status_code == 429),
        )
        or 0,
    )
    skipped_breakdown, fetch_failures_breakdown = _skipped_and_fetch_breakdowns(
        db,
        rate_limited_count=rate_limited_url_count,
    )
    total_skipped_rows = skipped_urls_count + policy_rejected_urls_count
    fetch_failure_row_count = max(0, total_crawl_errors - total_skipped_rows)

    # Combined HTTP status: pages (success path) + errors (failed fetches with status)
    combined_status_sql = text(
        """
        SELECT status_code, SUM(c)::bigint AS cnt FROM (
            SELECT status_code, COUNT(*)::bigint AS c
            FROM pages
            WHERE status_code IS NOT NULL
            GROUP BY status_code
            UNION ALL
            SELECT status_code, COUNT(*)::bigint AS c
            FROM crawl_errors
            WHERE status_code IS NOT NULL
            GROUP BY status_code
        ) sub
        GROUP BY status_code
        ORDER BY status_code
        """,
    )
    http_rows = list(db.execute(combined_status_sql).all())
    http_status_distribution = [
        HttpStatusCount(status_code=int(sc), count=int(c)) for sc, c in http_rows
    ]
    http_status_class_totals = _http_class_totals([(int(r[0]), int(r[1])) for r in http_rows])

    failed_url_rows = list(
        db.execute(
            select(
                CrawlError.url,
                CrawlError.error_type,
                CrawlError.error_message,
                CrawlError.created_at,
            )
            .order_by(CrawlError.created_at.desc())
            .limit(10),
        ).all(),
    )
    recent_failed_urls = [
        FailedUrlRead(url=str(u), error_type=str(et), error_message=em, created_at=ca)
        for u, et, em, ca in failed_url_rows
    ]

    timeout_fetch_count = int(
        db.scalar(
            select(func.count(CrawlError.id)).where(CrawlError.error_type == "timeout"),
        )
        or 0,
    )

    fd_rows = db.execute(
        text(
            """
            SELECT d, COUNT(*)::bigint FROM (
                SELECT lower((regexp_match(url, '^https?://([^/?#]+)', 'i'))[1]) AS d
                FROM crawl_errors
                WHERE url ~* '^https?://'
            ) s
            WHERE d IS NOT NULL AND d <> ''
            GROUP BY d
            ORDER BY COUNT(*) DESC
            LIMIT :lim
            """,
        ),
        {"lim": top_failure_domain_limit},
    ).all()
    top_failure_domains = [
        DomainFailureCount(domain=str(r[0]), failure_count=int(r[1])) for r in fd_rows
    ]

    return CrawlStatsRead(
        total_urls_attempted=total_urls_attempted,
        total_pages_crawled=total_pages_crawled,
        total_pages_indexed=total_pages_indexed,
        pages_pending_indexing=pages_pending_indexing,
        skipped_urls_count=skipped_urls_count,
        policy_rejected_urls_count=policy_rejected_urls_count,
        total_skipped_rows=total_skipped_rows,
        fetch_failure_row_count=fetch_failure_row_count,
        total_crawl_jobs=total_crawl_jobs,
        total_failures=total_crawl_errors,
        failed_url_count=failed_url_count,
        crawl_success_rate=crawl_success_rate,
        avg_pages_per_job=avg_pages_per_job,
        avg_crawl_duration_seconds=avg_crawl_duration_seconds,
        index_coverage=index_coverage,
        unique_terms=unique_terms,
        total_postings=total_postings,
        avg_terms_per_page=avg_terms_per_page,
        median_terms_per_page=median_terms_per_page,
        p95_terms_per_page=p95_terms_per_page,
        largest_page=largest_page,
        last_indexed_at=last_indexed_at,
        avg_fetch_latency_ms=avg_fetch_latency_ms,
        p95_fetch_latency_ms=p95_fetch_latency_ms,
        total_searches=total_searches,
        zero_result_searches=zero_result_searches,
        zero_result_rate=zero_result_rate,
        avg_results_per_search=avg_results_per_search,
        searches_hitting_result_cap=searches_hitting_result_cap,
        average_search_latency_ms=average_search_latency_ms,
        p95_search_latency_ms=p95_search_latency_ms,
        slowest_search_latency_ms=slowest_search_latency_ms,
        slowest_search_query=slowest_search_query,
        recent_searches=recent_searches,
        recent_zero_result_searches=recent_zero_result_searches,
        top_queries=top_queries,
        top_crawled_domains=top_crawled_domains,
        skipped_breakdown=skipped_breakdown,
        fetch_failures_breakdown=fetch_failures_breakdown,
        failures_by_type=failures_by_type,
        http_status_distribution=http_status_distribution,
        http_status_class_totals=http_status_class_totals,
        recent_failed_urls=recent_failed_urls,
        rate_limited_url_count=rate_limited_url_count,
        timeout_fetch_count=timeout_fetch_count,
        top_failure_domains=top_failure_domains,
    )

