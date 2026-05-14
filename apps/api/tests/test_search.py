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
from models.domain import CrawlJob, Page, PageGraphEdge, SearchQuery
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


def test_search_include_related_requires_job_id_422(client_mock_search_db) -> None:
    client, _ = client_mock_search_db
    r = client.get("/search?q=hello&include_related=true")
    assert r.status_code == 422
    detail = r.json().get("detail", "")
    assert "job_id" in str(detail).lower()


def test_search_related_limit_above_10_returns_422(client_mock_search_db) -> None:
    client, _ = client_mock_search_db
    r = client.get("/search?q=hello&job_id=1&include_related=true&related_limit=11")
    assert r.status_code == 422


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
            assert first.get("related") == []
            assert first.get("score_components") is None
            assert first.get("score_explanation") is None

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
            for hit in response.json()["results"]:
                assert hit.get("related") == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_search_include_related_graph_direction_dedupe_limit(test_database_url: str) -> None:
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
                    seed_url="https://rel.example/",
                    normalized_seed_url="https://rel.example/",
                    status="completed",
                )
                session.add(job)
                session.flush()

                p1 = Page(
                    crawl_job_id=job.id,
                    url="https://rel.example/p1",
                    normalized_url="https://rel.example/p1",
                    domain="rel.example",
                    title="GadgetRel Alpha Page",
                    extracted_text="unique gadgetrel one alpha alpha alpha",
                    status_code=200,
                    depth=0,
                    fetched_at=datetime.now(timezone.utc),
                )
                p2 = Page(
                    crawl_job_id=job.id,
                    url="https://rel.example/p2",
                    normalized_url="https://rel.example/p2",
                    domain="rel.example",
                    title="GadgetRel Beta",
                    extracted_text="unique gadgetrel one beta",
                    status_code=200,
                    depth=0,
                    fetched_at=datetime.now(timezone.utc),
                )
                p3 = Page(
                    crawl_job_id=job.id,
                    url="https://rel.example/p3",
                    normalized_url="https://rel.example/p3",
                    domain="rel.example",
                    title="GadgetRel Gamma",
                    extracted_text="unique gadgetrel one gamma",
                    status_code=200,
                    depth=0,
                    fetched_at=datetime.now(timezone.utc),
                )
                p4 = Page(
                    crawl_job_id=job.id,
                    url="https://rel.example/p4",
                    normalized_url="https://rel.example/p4",
                    domain="rel.example",
                    title="GadgetRel Delta",
                    extracted_text="unique gadgetrel one delta",
                    status_code=200,
                    depth=0,
                    fetched_at=datetime.now(timezone.utc),
                )
                session.add_all([p1, p2, p3, p4])
                session.flush()

                session.add_all(
                    [
                        PageGraphEdge(
                            crawl_job_id=job.id,
                            source_page_id=p4.id,
                            target_page_id=p1.id,
                            edge_type="link",
                            weight=1.0,
                            evidence={"source": "direct_internal_link"},
                        ),
                        PageGraphEdge(
                            crawl_job_id=job.id,
                            source_page_id=p1.id,
                            target_page_id=p2.id,
                            edge_type="link",
                            weight=0.5,
                            evidence={"source": "direct_internal_link"},
                        ),
                        PageGraphEdge(
                            crawl_job_id=job.id,
                            source_page_id=p1.id,
                            target_page_id=p2.id,
                            edge_type="url_hierarchy",
                            weight=0.9,
                            evidence={"parent_path": "/", "child_path": "/p2"},
                        ),
                        PageGraphEdge(
                            crawl_job_id=job.id,
                            source_page_id=p1.id,
                            target_page_id=p3.id,
                            edge_type="content_similarity",
                            weight=0.99,
                            evidence={"similarity": 0.99, "shared_terms": ["gamma"], "source": "x"},
                        ),
                    ],
                )
                session.commit()

                for pid in (p1.id, p2.id, p3.id, p4.id):
                    index_page(session, pid)
                session.commit()

                job_id = job.id
                p1_id, p2_id, p3_id, p4_id = p1.id, p2.id, p3.id, p4.id

            r = test_client.get(
                f"/search?q=gadgetrel%20alpha&job_id={job_id}&limit=5&include_related=true&related_limit=2",
            )
            assert r.status_code == 200, r.text
            body = r.json()
            hit = next(h for h in body["results"] if h["page_id"] == p1_id)
            rel = hit["related"]
            assert len(rel) == 2
            assert [x["page_id"] for x in rel] == [p4_id, p3_id]
            assert rel[0]["strength"] >= rel[1]["strength"]
            assert rel[0]["edge_type"] == "link"
            assert rel[0]["reason"]
            assert "Direct link" in rel[0]["reason"] or "link" in rel[0]["reason"].lower()
            p2_row = next((x for x in rel if x["page_id"] == p2_id), None)
            assert p2_row is None

            r2 = test_client.get(
                f"/search?q=gadgetrel%20alpha&job_id={job_id}&limit=5&include_related=true&related_limit=5",
            )
            hit2 = next(h for h in r2.json()["results"] if h["page_id"] == p1_id)
            ids5 = [x["page_id"] for x in hit2["related"]]
            assert p2_id in ids5
            p2_rel = next(x for x in hit2["related"] if x["page_id"] == p2_id)
            assert p2_rel["edge_type"] == "url_hierarchy"
            assert p2_rel["strength"] == 0.9
    finally:
        app.dependency_overrides.clear()
