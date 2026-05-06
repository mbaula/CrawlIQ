"""RQ enqueue endpoint."""

import pytest
from fastapi.testclient import TestClient

from main import app


def test_post_queue_ping_returns_job_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enqueue uses Redis/RQ; stub enqueue to avoid a running Redis in unit tests."""
    from routers import queue as queue_router

    def fake_enqueue(message: str = "ping") -> str:
        assert message == "hello"
        return "fake-job-id-123"

    monkeypatch.setattr(queue_router, "enqueue_ping_job", fake_enqueue)

    with TestClient(app) as client:
        response = client.post("/queue/ping", json={"message": "hello"})
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "fake-job-id-123"
    assert data["queue"] == "default"


def test_post_queue_ping_redis_error_503(monkeypatch: pytest.MonkeyPatch) -> None:
    import redis.exceptions

    from routers import queue as queue_router

    def boom(msg: str = "ping") -> str:
        raise redis.exceptions.ConnectionError("no redis")

    monkeypatch.setattr(queue_router, "enqueue_ping_job", boom)

    with TestClient(app) as client:
        response = client.post("/queue/ping", json={"message": "x"})
    assert response.status_code == 503
    assert "no redis" in response.json()["detail"]
