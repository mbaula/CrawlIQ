from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from db.session import get_db
from main import app
from models.domain import CrawlJob


@pytest.fixture
def client_mock_retry_db(monkeypatch: pytest.MonkeyPatch):
    mock_session = MagicMock()

    def _fake_enqueue(crawl_job_id: int) -> str:
        mock_session._enqueued_id = crawl_job_id
        return "test-rq-job-id"

    monkeypatch.setattr("routers.crawl_jobs.enqueue_process_crawl_job", _fake_enqueue)

    def _get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as test_client:
        yield test_client, mock_session
    app.dependency_overrides.clear()


def _job(status: str) -> CrawlJob:
    job = CrawlJob(
        seed_url="https://example.com/",
        normalized_seed_url="https://example.com/",
        status=status,
        max_pages=10,
        max_depth=1,
        same_domain_only=True,
    )
    job.id = 1
    job.pages_crawled = 2
    job.pages_indexed = 1
    job.pages_failed = 3
    job.created_at = datetime.now(timezone.utc)
    job.started_at = datetime.now(timezone.utc)
    job.finished_at = datetime.now(timezone.utc)
    job.error_message = "boom"
    return job


def test_retry_failed_job_requeues_and_clears_fields(client_mock_retry_db) -> None:
    client, session = client_mock_retry_db
    job = _job("failed")
    session.get.return_value = job

    resp = client.post("/crawl-jobs/1/retry")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == 1
    assert body["status"] == "queued"
    assert body["enqueued"] is True

    assert job.status == "queued"
    assert job.pages_crawled == 0
    assert job.pages_indexed == 0
    assert job.pages_failed == 0
    assert job.error_message is None
    assert job.started_at is None
    assert job.finished_at is None
    assert getattr(session, "_enqueued_id", None) == 1


def test_retry_non_failed_409(client_mock_retry_db) -> None:
    client, session = client_mock_retry_db
    session.get.return_value = _job("completed")
    resp = client.post("/crawl-jobs/1/retry")
    assert resp.status_code == 409

