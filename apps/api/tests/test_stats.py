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
    # `GET /stats` uses `execute()` several times; return safe empty results.
    def _execute(stmt):
        r = MagicMock()
        # Core job stats query uses `.one()`
        r.one.return_value = (0, 0, 0, 0)
        # Avg duration query uses `.scalar()`
        r.scalar.return_value = None
        # Largest page query uses `.first()`
        r.first.return_value = None
        # Top queries / domains / failures / http statuses / failed urls use `.all()`
        r.all.return_value = []
        return r

    mock_session.execute.side_effect = _execute

    # scalars are used for: failed_url_count, unique_terms, total_postings, avg_terms_result,
    # last_indexed_at, p95_result
    mock_session.scalar.side_effect = [0, 0, 0, 0, None, 0]

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

