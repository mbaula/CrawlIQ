from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from db.session import get_db
from main import app
from models.domain import CrawlJob


@pytest.fixture
def client_mock_cancel_db():
    mock_session = MagicMock()

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
    job.pages_crawled = 0
    job.pages_indexed = 0
    job.pages_failed = 0
    job.created_at = datetime.now(timezone.utc)
    job.started_at = None
    job.finished_at = None
    job.error_message = None
    return job


def test_cancel_job_sets_status_cancelled(client_mock_cancel_db) -> None:
    client, session = client_mock_cancel_db
    job = _job("running")
    session.get.return_value = job
    session.scalar.return_value = 0

    resp = client.post("/crawl-jobs/1/cancel")
    assert resp.status_code == 200, resp.text
    assert job.status == "cancelled"
    assert resp.json()["status"] == "cancelled"


def test_cancel_job_completed_409(client_mock_cancel_db) -> None:
    client, session = client_mock_cancel_db
    session.get.return_value = _job("completed")
    resp = client.post("/crawl-jobs/1/cancel")
    assert resp.status_code == 409

