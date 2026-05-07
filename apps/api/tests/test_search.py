"""Tests for ``GET /search``."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from db.session import get_db
from main import app
from models.domain import CrawlJob, Page, SearchQuery
from services.index_page import index_page


@pytest.fixture
def client_mock_search_db():
    mock_session = MagicMock()

    def _get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as test_client:
        yield test_client, mock_session
    app.dependency_overrides.clear()


def test_search_whitespace_only_query_422(client_mock_search_db) -> None:
    client, _ = client_mock_search_db
    response = client.get("/search?q=%20%20%20")
    assert response.status_code == 422


def test_search_unknown_job_404(client_mock_search_db) -> None:
    client, mock_session = client_mock_search_db
    mock_session.get.return_value = None
    response = client.get("/search?q=hello&job_id=999")
    assert response.status_code == 404


def test_search_stats_returns_rows(client_mock_search_db) -> None:
    client, mock_session = client_mock_search_db
    row = SearchQuery(
        query="hello",
        result_count=2,
        latency_ms=5,
    )
    row.created_at = datetime.now(timezone.utc)
    mock_session.scalars.return_value.all.return_value = [row]

    response = client.get("/search/stats?limit=10")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recent"][0]["query"] == "hello"
    assert body["recent"][0]["result_count"] == 2
    assert body["recent"][0]["latency_ms"] == 5
    assert body["recent"][0]["created_at"]


@pytest.mark.integration
def test_search_returns_hits_and_logs_query(test_database_url: str) -> None:
    from db.url import sync_engine_url

    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    try:
        with TestClient(app) as test_client:
            with SessionLocal() as session:
                job_a = CrawlJob(
                    seed_url="https://sa.example/",
                    normalized_seed_url="https://sa.example/",
                    status="completed",
                )
                job_b = CrawlJob(
                    seed_url="https://sb.example/",
                    normalized_seed_url="https://sb.example/",
                    status="completed",
                )
                session.add(job_a)
                session.add(job_b)
                session.commit()

                p_alpha = Page(
                    crawl_job_id=job_a.id,
                    url="https://sa.example/a",
                    normalized_url="https://sa.example/a",
                    domain="sa.example",
                    title="FastAPI",
                    extracted_text="FastAPI is a modern async Python framework for APIs.",
                    status_code=200,
                    depth=0,
                    fetched_at=datetime.now(timezone.utc),
                )
                p_beta = Page(
                    crawl_job_id=job_b.id,
                    url="https://sb.example/b",
                    normalized_url="https://sb.example/b",
                    domain="sb.example",
                    title="Redis",
                    extracted_text="Redis is an in-memory data store used with FastAPI sometimes.",
                    status_code=200,
                    depth=0,
                    fetched_at=datetime.now(timezone.utc),
                )
                session.add(p_alpha)
                session.add(p_beta)
                session.commit()

                index_page(session, p_alpha.id)
                index_page(session, p_beta.id)
                session.commit()

                job_a_id, job_b_id = job_a.id, job_b.id
                alpha_id, beta_id = p_alpha.id, p_beta.id

            response = test_client.get(f"/search?q=fastapi%20async&job_id={job_a_id}&limit=10")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["query"] == "fastapi async"
            assert body["result_count"] >= 1
            assert body["latency_ms"] >= 0
            ids = {hit["page_id"] for hit in body["results"]}
            assert alpha_id in ids
            assert beta_id not in ids

            first = next(h for h in body["results"] if h["page_id"] == alpha_id)
            assert "async" in first["matched_terms"] or "fastapi" in first["matched_terms"]
            assert first["score"] > 0
            assert first["snippet"]

        with SessionLocal() as session:
            logged = session.scalar(select(SearchQuery).order_by(SearchQuery.id.desc()).limit(1))
            assert logged is not None
            assert logged.query == "fastapi async"
            assert logged.result_count >= 1
            assert logged.latency_ms >= 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_search_without_job_id_sees_multiple_jobs(test_database_url: str) -> None:
    from db.url import sync_engine_url

    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    try:
        with TestClient(app) as test_client:
            with SessionLocal() as session:
                job = CrawlJob(
                    seed_url="https://sc.example/",
                    normalized_seed_url="https://sc.example/",
                    status="completed",
                )
                session.add(job)
                session.commit()

                p1 = Page(
                    crawl_job_id=job.id,
                    url="https://sc.example/one",
                    normalized_url="https://sc.example/one",
                    domain="sc.example",
                    title="Alpha",
                    extracted_text="Unique zebrazon keyword one",
                    status_code=200,
                    depth=0,
                )
                p2 = Page(
                    crawl_job_id=job.id,
                    url="https://sc.example/two",
                    normalized_url="https://sc.example/two",
                    domain="sc.example",
                    title="Beta",
                    extracted_text="Unique zebrazon keyword two",
                    status_code=200,
                    depth=0,
                )
                session.add(p1)
                session.add(p2)
                session.commit()
                index_page(session, p1.id)
                index_page(session, p2.id)
                session.commit()

            response = test_client.get("/search?q=zebrazon&limit=10")
            assert response.status_code == 200, response.text
            assert response.json()["result_count"] == 2
    finally:
        app.dependency_overrides.clear()
