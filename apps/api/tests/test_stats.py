"""Tests for ``GET /stats``."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from db.session import get_db
from main import app


def test_stats_endpoint_returns_payload(monkeypatch) -> None:
    mock_session = MagicMock()

    execute_jobs = MagicMock()
    execute_jobs.one.return_value = (0, 0, 0, 0)
    execute_domains = MagicMock()
    execute_domains.all.return_value = []
    mock_session.execute.side_effect = [execute_jobs, execute_domains]

    # failed_url_count, avg_latency
    mock_session.scalar.side_effect = [0, 0]

    # recent searches
    mock_session.scalars.return_value.all.return_value = []

    def _get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _get_db
    try:
        with TestClient(app) as client:
            resp = client.get("/stats")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["total_crawl_jobs"] == 0
            assert body["total_pages_crawled"] == 0
            assert body["total_pages_indexed"] == 0
            assert body["total_failures"] == 0
            assert body["failed_url_count"] == 0
            assert body["recent_searches"] == []
            assert body["top_crawled_domains"] == []
    finally:
        app.dependency_overrides.clear()

