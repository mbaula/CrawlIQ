"""Tests for ``GET /stats``."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from db.session import get_db
from main import app


def test_stats_endpoint_returns_payload() -> None:
    mock_session = MagicMock()

    exec_result = MagicMock()
    exec_result.one.side_effect = [
        (0,),  # job count
        (0, 0, 0, 0),  # search stats row
    ]
    exec_result.scalar.return_value = None
    exec_result.first.return_value = None
    exec_result.all.return_value = []
    mock_session.execute.return_value = exec_result
    mock_session.scalar.return_value = 0

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
            assert body["total_urls_attempted"] == 0
            assert body["median_terms_per_page"] == 0.0
            assert body["http_status_class_totals"]["status_2xx"] == 0
            assert body["recent_searches"] == []
            assert body["top_crawled_domains"] == []
    finally:
        app.dependency_overrides.clear()


def test_http_class_totals_buckets() -> None:
    from routers.stats import _http_class_totals

    rows = [(200, 3), (301, 1), (404, 5), (500, 2)]
    t = _http_class_totals(rows)
    assert t.status_2xx == 3
    assert t.status_3xx == 1
    assert t.status_4xx == 5
    assert t.status_5xx == 2
