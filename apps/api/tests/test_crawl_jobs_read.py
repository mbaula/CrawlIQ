"""GET ``/crawl-jobs`` and related read endpoints."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from db.session import get_db
from main import app
from models.domain import CrawlError, CrawlJob, Page


@pytest.fixture
def client_mock_read_db():
    mock_session = MagicMock()

    def _get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as test_client:
        yield test_client, mock_session
    app.dependency_overrides.clear()


def _sample_job() -> CrawlJob:
    job = CrawlJob(
        seed_url="https://example.com/",
        normalized_seed_url="https://example.com/",
        status="queued",
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


def test_list_crawl_jobs_empty(client_mock_read_db: tuple[TestClient, MagicMock]) -> None:
    client, mock_session = client_mock_read_db
    mock_session.scalars.return_value.all.return_value = []
    response = client.get("/crawl-jobs")
    assert response.status_code == 200, response.text
    assert response.json() == []


def test_list_crawl_jobs_returns_rows(client_mock_read_db: tuple[TestClient, MagicMock]) -> None:
    client, mock_session = client_mock_read_db
    job = _sample_job()
    mock_session.scalars.return_value.all.return_value = [job]
    response = client.get("/crawl-jobs")
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["status"] == "queued"
    assert data[0]["normalized_seed_url"] == "https://example.com/"


def test_list_crawl_jobs_limit_validation(client_mock_read_db: tuple[TestClient, MagicMock]) -> None:
    client, _ = client_mock_read_db
    response = client.get("/crawl-jobs?limit=0")
    assert response.status_code == 422


def test_get_crawl_job_404(client_mock_read_db: tuple[TestClient, MagicMock]) -> None:
    client, mock_session = client_mock_read_db
    mock_session.get.return_value = None
    response = client.get("/crawl-jobs/999")
    assert response.status_code == 404


def test_get_crawl_job_200(client_mock_read_db: tuple[TestClient, MagicMock]) -> None:
    client, mock_session = client_mock_read_db
    job = _sample_job()
    mock_session.get.return_value = job
    response = client.get("/crawl-jobs/1")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == 1
    assert response.json()["pages_crawled"] == 0


def test_list_pages_job_missing_404(client_mock_read_db: tuple[TestClient, MagicMock]) -> None:
    client, mock_session = client_mock_read_db
    mock_session.get.return_value = None
    response = client.get("/crawl-jobs/1/pages")
    assert response.status_code == 404


def test_list_pages_empty(client_mock_read_db: tuple[TestClient, MagicMock]) -> None:
    client, mock_session = client_mock_read_db
    mock_session.get.return_value = _sample_job()
    mock_session.scalars.return_value.all.return_value = []
    response = client.get("/crawl-jobs/1/pages")
    assert response.status_code == 200, response.text
    assert response.json() == []


def test_list_errors_job_missing_404(client_mock_read_db: tuple[TestClient, MagicMock]) -> None:
    client, mock_session = client_mock_read_db
    mock_session.get.return_value = None
    response = client.get("/crawl-jobs/1/errors")
    assert response.status_code == 404


def test_list_errors_empty(client_mock_read_db: tuple[TestClient, MagicMock]) -> None:
    client, mock_session = client_mock_read_db
    mock_session.get.return_value = _sample_job()
    mock_session.scalars.return_value.all.return_value = []
    response = client.get("/crawl-jobs/1/errors")
    assert response.status_code == 200, response.text
    assert response.json() == []


@pytest.mark.integration
def test_read_endpoints_postgres(test_database_url: str) -> None:
    from sqlalchemy import create_engine

    from db.url import sync_engine_url

    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    try:
        with TestClient(app) as test_client:
            create_resp = test_client.post(
                "/crawl-jobs",
                json={
                    "seed_url": "https://read-test.example/",
                    "max_pages": 5,
                    "max_depth": 0,
                    "same_domain_only": True,
                },
            )
            assert create_resp.status_code == 200, create_resp.text
            job_id = create_resp.json()["id"]

            list_resp = test_client.get("/crawl-jobs")
            assert list_resp.status_code == 200
            ids = {row["id"] for row in list_resp.json()}
            assert job_id in ids

            one = test_client.get(f"/crawl-jobs/{job_id}")
            assert one.status_code == 200
            assert one.json()["seed_url"] == "https://read-test.example/"
            assert one.json()["normalized_seed_url"].startswith("http")

            pages = test_client.get(f"/crawl-jobs/{job_id}/pages")
            assert pages.status_code == 200
            assert pages.json() == []

            errors = test_client.get(f"/crawl-jobs/{job_id}/errors")
            assert errors.status_code == 200
            assert errors.json() == []

            missing = test_client.get("/crawl-jobs/999999999")
            assert missing.status_code == 404

            session = TestSession()
            try:
                job = session.get(CrawlJob, job_id)
                assert job is not None
                page = Page(
                    crawl_job_id=job_id,
                    url="https://read-test.example/p",
                    normalized_url="https://read-test.example/p",
                    domain="read-test.example",
                    title="T",
                    depth=0,
                    status_code=200,
                )
                err = CrawlError(
                    crawl_job_id=job_id,
                    url="https://read-test.example/bad",
                    normalized_url="https://read-test.example/bad",
                    error_type="fetch",
                    error_message="oops",
                )
                session.add(page)
                session.add(err)
                session.commit()
            finally:
                session.close()

            pages2 = test_client.get(f"/crawl-jobs/{job_id}/pages")
            assert pages2.status_code == 200
            assert len(pages2.json()) == 1
            assert pages2.json()[0]["url"] == "https://read-test.example/p"

            err_resp = test_client.get(f"/crawl-jobs/{job_id}/errors")
            assert err_resp.status_code == 200
            assert len(err_resp.json()) == 1
            assert err_resp.json()[0]["error_type"] == "fetch"
    finally:
        app.dependency_overrides.clear()
