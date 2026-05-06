"""Integration tests for worker ``process_crawl_job``."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db import session as session_mod
from db.url import sync_engine_url
from models.domain import CrawlJob
from schemas.fetch_html import FetchHtmlFailure, FetchHtmlSuccess
from services.urlnorm import normalize_seed_url

_API_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _API_ROOT.parent.parent
_WORKER_ROOT = _REPO_ROOT / "apps" / "worker"


def _import_worker_jobs():  # noqa: ANN202
    if str(_WORKER_ROOT) not in sys.path:
        sys.path.insert(0, str(_WORKER_ROOT))
    import jobs as worker_jobs  # noqa: PLC0415

    return worker_jobs


def _reset_cached_engine() -> None:
    eng = session_mod._engine
    if eng is not None:
        eng.dispose()
    session_mod._engine = None
    session_mod._session_factory = None


@pytest.mark.integration
def test_process_crawl_job_marks_completed(
    test_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    _reset_cached_engine()

    worker_jobs = _import_worker_jobs()

    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    seed = "https://example.com/worker-process-test-ok"
    job = CrawlJob(
        seed_url=seed,
        normalized_seed_url=normalize_seed_url(seed),
        status="queued",
        max_pages=10,
        max_depth=1,
        same_domain_only=True,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    job_id = job.id
    session.close()

    def fake_fetch(url: str, settings=None, client=None):  # noqa: ANN001
        return FetchHtmlSuccess(
            url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            html="<html><head><title>T</title></head><body>x</body></html>",
            elapsed_ms=1,
        )

    monkeypatch.setattr("services.crawl_persistence.fetch_html", fake_fetch)

    worker_jobs.process_crawl_job(job_id)

    session2 = Session()
    row = session2.get(CrawlJob, job_id)
    assert row is not None
    assert row.status == "completed"
    assert row.finished_at is not None
    assert row.error_message is None
    session2.close()


@pytest.mark.integration
def test_process_crawl_job_fetch_failure_marks_failed(
    test_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    _reset_cached_engine()

    worker_jobs = _import_worker_jobs()

    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    seed = "https://example.com/worker-process-test-fail"
    job = CrawlJob(
        seed_url=seed,
        normalized_seed_url=normalize_seed_url(seed),
        status="queued",
        max_pages=10,
        max_depth=1,
        same_domain_only=True,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    job_id = job.id
    session.close()

    def fake_fetch(url: str, settings=None, client=None):  # noqa: ANN001
        return FetchHtmlFailure(
            url=url,
            kind="http_error",
            reason="upstream 500",
            status_code=500,
        )

    monkeypatch.setattr("services.crawl_persistence.fetch_html", fake_fetch)

    worker_jobs.process_crawl_job(job_id)

    session2 = Session()
    row = session2.get(CrawlJob, job_id)
    assert row is not None
    assert row.status == "failed"
    assert row.finished_at is not None
    assert row.error_message is not None
    session2.close()
