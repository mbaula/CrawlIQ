from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from db.session import get_db
from main import app


@pytest.fixture
def client_mock_db(monkeypatch: pytest.MonkeyPatch):
    """In-memory fake session: Postgres ``Identity()`` PKs do not match SQLite in tests."""

    state: dict = {}

    class FakeSession:
        def add(self, obj: object) -> None:
            state["job"] = obj

        def commit(self) -> None:
            job = state["job"]
            job.id = 1
            job.pages_crawled = 0
            job.pages_indexed = 0
            job.pages_failed = 0
            job.created_at = datetime.now(timezone.utc)

        def refresh(self, obj: object) -> None:
            pass

    fake = FakeSession()

    def _fake_enqueue(crawl_job_id: int) -> str:
        state["enqueued_id"] = crawl_job_id
        return "test-rq-job-id"

    monkeypatch.setattr("routers.crawl_jobs.enqueue_process_crawl_job", _fake_enqueue)

    def _get_db():
        yield fake

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_normalize_seed_url_https() -> None:
    from services.urlnorm import normalize_seed_url

    assert normalize_seed_url("  HTTPS://Example.COM/path ") == "https://example.com/path"


def test_normalize_seed_url_empty_raises() -> None:
    from services.urlnorm import normalize_seed_url

    with pytest.raises(ValueError, match="empty"):
        normalize_seed_url("   ")


def test_normalize_seed_url_scheme_raises() -> None:
    from services.urlnorm import normalize_seed_url

    with pytest.raises(ValueError, match="http"):
        normalize_seed_url("ftp://example.com/")


def test_post_crawl_job_created(client_mock_db: TestClient) -> None:
    response = client_mock_db.post(
        "/crawl-jobs",
        json={
            "seed_url": "https://fastapi.tiangolo.com/",
            "max_pages": 500,
            "max_depth": 3,
            "same_domain_only": True,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "queued"
    assert data["max_pages"] == 500
    assert data["max_depth"] == 3
    assert data["same_domain_only"] is True
    assert data["seed_url"] == "https://fastapi.tiangolo.com/"
    assert isinstance(data["id"], int)
    assert data["created_at"]
    assert data.get("enqueued") is True


def test_post_crawl_job_normalize_fails_400(
    client_mock_db: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _bad(_: str) -> str:
        raise ValueError("rejected by policy")

    monkeypatch.setattr("routers.crawl_jobs.normalize_seed_url", _bad)
    response = client_mock_db.post(
        "/crawl-jobs",
        json={
            "seed_url": "https://example.com/",
            "max_pages": 1,
            "max_depth": 0,
            "same_domain_only": True,
        },
    )
    assert response.status_code == 400
    assert "rejected" in response.json()["detail"]


def test_post_crawl_job_invalid_bounds(client_mock_db: TestClient) -> None:
    response = client_mock_db.post(
        "/crawl-jobs",
        json={
            "seed_url": "https://example.com/",
            "max_pages": 0,
            "max_depth": 0,
            "same_domain_only": True,
        },
    )
    assert response.status_code == 422


@pytest.mark.integration
def test_post_crawl_job_postgres(
    test_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from db.url import sync_engine_url

    monkeypatch.setattr(
        "routers.crawl_jobs.enqueue_process_crawl_job",
        lambda _jid: "integration-test-rq-id",
    )

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
            response = test_client.post(
                "/crawl-jobs",
                json={
                    "seed_url": "https://example.org/",
                    "max_pages": 10,
                    "max_depth": 1,
                    "same_domain_only": False,
                },
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "queued"
        assert body.get("enqueued") is True
    finally:
        app.dependency_overrides.clear()


def test_post_crawl_job_enqueue_redis_failure_sets_enqueued_false(
    client_mock_db: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import redis.exceptions

    def _boom(_jid: int) -> str:
        raise redis.exceptions.ConnectionError("test redis down")

    monkeypatch.setattr("routers.crawl_jobs.enqueue_process_crawl_job", _boom)
    response = client_mock_db.post(
        "/crawl-jobs",
        json={
            "seed_url": "https://example.com/",
            "max_pages": 1,
            "max_depth": 0,
            "same_domain_only": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"
    assert response.json().get("enqueued") is False
