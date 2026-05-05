"""Fetch one URL, parse HTML, persist ``pages`` / ``page_links`` / ``crawl_errors``.

Intended as the unit of work for one frontier step; the worker can call this later.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from yarl import URL

from config import Settings, get_settings
from models.domain import CrawlError, CrawlJob, Page, PageLink
from schemas.crawl_persistence import CrawlPersistResult
from schemas.fetch_html import FetchHtmlFailure
from services.fetch_html import fetch_html
from services.parse_html import parse_html
from services.urlnorm import normalize_url


def _sha256_utf8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _error_normalized_key(url: str) -> str:
    raw = url.strip()
    if not raw:
        return ""
    try:
        return normalize_url(raw)
    except ValueError:
        return raw


def _seed_host_lower(job: CrawlJob) -> str | None:
    try:
        h = URL(job.normalized_seed_url).host
        return h.lower() if h else None
    except ValueError:
        return None


def _link_host_lower(normalized_link: str) -> str | None:
    try:
        h = URL(normalized_link).host
        return h.lower() if h else None
    except ValueError:
        return None


def _is_crawl_eligible_target(normalized_link: str, job: CrawlJob) -> bool:
    host = _link_host_lower(normalized_link)
    if not host:
        return False
    if not job.same_domain_only:
        return True
    seed = _seed_host_lower(job)
    if not seed:
        return False
    return host == seed


def _record_crawl_error(
    session: Session,
    job: CrawlJob,
    *,
    url: str,
    norm_key: str,
    error_type: str,
    error_message: str | None,
) -> None:
    err = session.scalar(
        select(CrawlError).where(
            CrawlError.crawl_job_id == job.id,
            CrawlError.normalized_url == norm_key,
        ),
    )
    if err is not None:
        err.url = url
        err.error_type = error_type
        err.error_message = error_message
        err.retry_count = err.retry_count + 1
        err.updated_at = datetime.now(timezone.utc)
    else:
        session.add(
            CrawlError(
                crawl_job_id=job.id,
                url=url,
                normalized_url=norm_key,
                error_type=error_type,
                error_message=error_message,
            ),
        )


def crawl_and_persist_page(
    session: Session,
    job_id: int,
    url: str,
    *,
    depth: int = 0,
    settings: Settings | None = None,
    http_client: httpx.Client | None = None,
) -> CrawlPersistResult:
    """
    Fetch ``url``, parse, and persist one page for ``job_id``.

    Does not call ``commit``; the caller owns the transaction.
    On failure paths, flushes error rows so the caller can commit.
    """
    settings = settings or get_settings()
    job = session.get(CrawlJob, job_id)
    if job is None:
        return CrawlPersistResult(
            status="failed",
            normalized_url="",
            error_type="job_not_found",
            error_message=f"crawl job {job_id} does not exist",
        )

    fetch_out = fetch_html(url, settings=settings, client=http_client)
    if isinstance(fetch_out, FetchHtmlFailure):
        norm_key = _error_normalized_key(url)
        _record_crawl_error(
            session,
            job,
            url=url.strip(),
            norm_key=norm_key or url.strip(),
            error_type=fetch_out.kind,
            error_message=fetch_out.reason,
        )
        job.pages_failed = job.pages_failed + 1
        session.flush()
        return CrawlPersistResult(
            status="failed",
            normalized_url=norm_key or url.strip(),
            error_type=fetch_out.kind,
            error_message=fetch_out.reason,
        )

    final_url = fetch_out.final_url
    try:
        normalized_page_url = normalize_url(final_url)
    except ValueError as exc:
        _record_crawl_error(
            session,
            job,
            url=final_url,
            norm_key=final_url.strip(),
            error_type="invalid_url",
            error_message=str(exc),
        )
        job.pages_failed = job.pages_failed + 1
        session.flush()
        return CrawlPersistResult(
            status="failed",
            normalized_url=final_url.strip(),
            error_type="invalid_url",
            error_message=str(exc),
        )

    existing_id = session.scalar(
        select(Page.id).where(
            Page.crawl_job_id == job_id,
            Page.normalized_url == normalized_page_url,
        ),
    )
    if existing_id is not None:
        return CrawlPersistResult(
            status="duplicate",
            page_id=existing_id,
            normalized_url=normalized_page_url,
            links_saved=0,
        )

    try:
        parsed = parse_html(fetch_out.html, base_url=final_url)
    except Exception as exc:  # noqa: BLE001 — surface parse bugs as crawl errors
        _record_crawl_error(
            session,
            job,
            url=final_url,
            norm_key=normalized_page_url,
            error_type="parse_error",
            error_message=str(exc),
        )
        job.pages_failed = job.pages_failed + 1
        session.flush()
        return CrawlPersistResult(
            status="failed",
            normalized_url=normalized_page_url,
            error_type="parse_error",
            error_message=str(exc),
        )

    raw_hash = _sha256_utf8(fetch_out.html)
    content_hash = _sha256_utf8(parsed.text)
    domain_host = _link_host_lower(normalized_page_url) or ""

    page = Page(
        crawl_job_id=job_id,
        url=final_url,
        normalized_url=normalized_page_url,
        domain=domain_host,
        title=parsed.title or None,
        raw_html_hash=raw_hash,
        content_hash=content_hash,
        extracted_text=parsed.text,
        status_code=fetch_out.status_code,
        depth=depth,
        fetched_at=datetime.now(timezone.utc),
    )

    try:
        with session.begin_nested():
            session.add(page)
            session.flush()
    except IntegrityError:
        dup_id = session.scalar(
            select(Page.id).where(
                Page.crawl_job_id == job_id,
                Page.normalized_url == normalized_page_url,
            ),
        )
        return CrawlPersistResult(
            status="duplicate",
            page_id=dup_id,
            normalized_url=normalized_page_url,
            links_saved=0,
        )

    links_saved = 0
    for target in parsed.links:
        eligible = _is_crawl_eligible_target(target, job)
        session.add(
            PageLink(
                crawl_job_id=job_id,
                source_page_id=page.id,
                target_normalized_url=target,
                depth=depth + 1,
                is_crawl_eligible=eligible,
            ),
        )
        links_saved += 1

    job.pages_crawled = job.pages_crawled + 1
    if job.started_at is None:
        job.started_at = datetime.now(timezone.utc)

    session.flush()

    return CrawlPersistResult(
        status="saved",
        page_id=page.id,
        normalized_url=normalized_page_url,
        links_saved=links_saved,
    )
