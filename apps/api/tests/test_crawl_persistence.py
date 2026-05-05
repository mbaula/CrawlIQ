"""Single-page crawl persistence (Postgres integration + mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from config import Settings
from db.url import sync_engine_url
from models.domain import CrawlError, CrawlJob, Page, PageLink
from services.crawl_persistence import crawl_and_persist_page


def _session_factory(test_database_url: str) -> sessionmaker[Session]:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _html_with_links() -> bytes:
    return b"""<!DOCTYPE html>
<html><head><title>Seed T</title></head><body>
<p>Body hello</p>
<a href="/relative">Rel</a>
<a href="https://other.example/page">External</a>
</body></html>"""


@pytest.mark.integration
def test_crawl_persist_saved_and_links_eligibility(test_database_url: str) -> None:
    mk = _session_factory(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://example.com/seed",
            normalized_seed_url="https://example.com/seed",
            status="queued",
            same_domain_only=True,
        )
        session.add(job)
        session.commit()
        job_id = job.id

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "example.com"
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=_html_with_links(),
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        transport=transport,
        follow_redirects=True,
        max_redirects=10,
        timeout=httpx.Timeout(30.0),
    ) as client:
        with mk() as session:
            job = session.get(CrawlJob, job_id)
            assert job is not None
            before_crawled = job.pages_crawled
            result = crawl_and_persist_page(
                session,
                job_id,
                "https://example.com/seed",
                depth=0,
                settings=Settings(),
                http_client=client,
            )
            session.commit()

    assert result.status == "saved"
    assert result.page_id is not None
    assert result.links_saved == 2
    assert "example.com" in result.normalized_url

    with mk() as session:
        page = session.scalar(select(Page).where(Page.id == result.page_id))
        assert page is not None
        assert page.title == "Seed T"
        assert "Body hello" in (page.extracted_text or "")
        assert page.status_code == 200
        assert page.raw_html_hash and page.content_hash
        assert page.depth == 0
        job2 = session.get(CrawlJob, job_id)
        assert job2 is not None
        assert job2.pages_crawled == before_crawled + 1
        assert job2.started_at is not None

        links = session.scalars(
            select(PageLink).where(PageLink.source_page_id == page.id),
        ).all()
        assert len(links) == 2
        by_target = {pl.target_normalized_url: pl for pl in links}
        internal = by_target.get("https://example.com/relative")
        external = by_target.get("https://other.example/page")
        assert internal is not None and internal.is_crawl_eligible is True
        assert external is not None and external.is_crawl_eligible is False


@pytest.mark.integration
def test_crawl_persist_duplicate_no_extra_crawl_count(test_database_url: str) -> None:
    mk = _session_factory(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://dup.example/",
            normalized_seed_url="https://dup.example/",
            status="queued",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    body = _html_with_links()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=body,
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        transport=transport,
        follow_redirects=True,
        max_redirects=10,
        timeout=httpx.Timeout(30.0),
    ) as client:
        with mk() as session:
            r1 = crawl_and_persist_page(
                session,
                job_id,
                "https://dup.example/start",
                http_client=client,
                settings=Settings(),
            )
            session.commit()
        with mk() as session:
            crawled_after_first = session.get(CrawlJob, job_id).pages_crawled
            r2 = crawl_and_persist_page(
                session,
                job_id,
                "https://dup.example/start",
                http_client=client,
                settings=Settings(),
            )
            session.commit()

    assert r1.status == "saved"
    assert r2.status == "duplicate"
    assert r1.page_id == r2.page_id

    with mk() as session:
        job = session.get(CrawlJob, job_id)
        assert job.pages_crawled == crawled_after_first
        assert len(session.scalars(select(Page).where(Page.crawl_job_id == job_id)).all()) == 1


@pytest.mark.integration
def test_crawl_persist_fetch_failure_records_error(test_database_url: str) -> None:
    mk = _session_factory(test_database_url)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"nope")

    transport = httpx.MockTransport(handler)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://fail.example/",
            normalized_seed_url="https://fail.example/",
            status="queued",
        )
        session.add(job)
        session.commit()
        job_id = job.id
        before_failed = job.pages_failed

    with httpx.Client(
        transport=transport,
        follow_redirects=True,
        max_redirects=10,
        timeout=httpx.Timeout(30.0),
    ) as client:
        with mk() as session:
            result = crawl_and_persist_page(
                session,
                job_id,
                "https://fail.example/missing",
                http_client=client,
                settings=Settings(),
            )
            session.commit()

    assert result.status == "failed"
    assert result.error_type == "http_error"

    with mk() as session:
        job = session.get(CrawlJob, job_id)
        assert job.pages_failed == before_failed + 1
        err = session.scalar(select(CrawlError).where(CrawlError.crawl_job_id == job_id))
        assert err is not None
        assert err.error_type == "http_error"


@pytest.mark.integration
def test_crawl_persist_parse_failure(test_database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    mk = _session_factory(test_database_url)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"<html><title>x</title><body>ok</body></html>",
        )

    transport = httpx.MockTransport(handler)

    def boom(html: str, base_url: str):
        raise RuntimeError("parse exploded")

    monkeypatch.setattr("services.crawl_persistence.parse_html", boom)

    with mk() as session:
        job = CrawlJob(
            seed_url="https://parse.fail/",
            normalized_seed_url="https://parse.fail/",
            status="queued",
        )
        session.add(job)
        session.commit()
        job_id = job.id
        before_failed = job.pages_failed

    with httpx.Client(
        transport=transport,
        follow_redirects=True,
        max_redirects=10,
        timeout=httpx.Timeout(30.0),
    ) as client:
        with mk() as session:
            result = crawl_and_persist_page(
                session,
                job_id,
                "https://parse.fail/",
                http_client=client,
                settings=Settings(),
            )
            session.commit()

    assert result.status == "failed"
    assert result.error_type == "parse_error"

    with mk() as session:
        job = session.get(CrawlJob, job_id)
        assert job.pages_failed == before_failed + 1
        err = session.scalar(select(CrawlError).where(CrawlError.crawl_job_id == job_id))
        assert err is not None
        assert err.error_type == "parse_error"
        assert len(session.scalars(select(Page).where(Page.crawl_job_id == job_id)).all()) == 0


@pytest.mark.integration
def test_same_domain_off_all_links_eligible(test_database_url: str) -> None:
    mk = _session_factory(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://open.example/",
            normalized_seed_url="https://open.example/",
            status="queued",
            same_domain_only=False,
        )
        session.add(job)
        session.commit()
        job_id = job.id

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=_html_with_links(),
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        transport=transport,
        follow_redirects=True,
        max_redirects=10,
        timeout=httpx.Timeout(30.0),
    ) as client:
        with mk() as session:
            result = crawl_and_persist_page(
                session,
                job_id,
                "https://open.example/",
                http_client=client,
                settings=Settings(),
            )
            session.commit()

    assert result.status == "saved"
    with mk() as session:
        page = session.scalar(select(Page).where(Page.id == result.page_id))
        links = session.scalars(select(PageLink).where(PageLink.source_page_id == page.id)).all()
        assert all(pl.is_crawl_eligible for pl in links)
