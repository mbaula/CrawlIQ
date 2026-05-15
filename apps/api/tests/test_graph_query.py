"""Tests for ``GET /graph/query`` (Sprint 11)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.session import get_db
from main import app
from models.domain import CrawlJob, Page, PageGraphEdge
from services.index_page import index_page
from services.page_graph_query import _JobPoolStats, _select_best_job


def test_graph_query_whitespace_only_422() -> None:
    mock_session = MagicMock()

    def _get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _get_db
    try:
        with TestClient(app) as client:
            r = client.get("/graph/query", params={"q": "   "})
            assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_graph_query_unknown_job_404() -> None:
    mock_session = MagicMock()
    mock_session.get.return_value = None

    def _get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _get_db
    try:
        with TestClient(app) as client:
            r = client.get("/graph/query", params={"q": "hello", "job_id": 999_999_999})
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_select_best_job_tie_breakers() -> None:
    t = datetime(2024, 6, 1, tzinfo=timezone.utc)
    assert (
        _select_best_job(
            [
                _JobPoolStats(1, 5.0, 1, t),
                _JobPoolStats(2, 6.0, 1, t),
            ],
        ).crawl_job_id
        == 2
    )

    assert (
        _select_best_job(
            [
                _JobPoolStats(1, 5.0, 1, t),
                _JobPoolStats(2, 5.0, 3, t),
            ],
        ).crawl_job_id
        == 2
    )

    t_old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    t_new = datetime(2021, 1, 1, tzinfo=timezone.utc)
    assert (
        _select_best_job(
            [
                _JobPoolStats(1, 5.0, 2, t_old),
                _JobPoolStats(2, 5.0, 2, t_new),
            ],
        ).crawl_job_id
        == 2
    )

    assert (
        _select_best_job(
            [
                _JobPoolStats(1, 5.0, 2, t),
                _JobPoolStats(2, 5.0, 2, t),
            ],
        ).crawl_job_id
        == 2
    )


@pytest.fixture
def graph_query_client(test_database_url: str):
    from db.url import sync_engine_url

    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()

    def _get_db():
        yield session

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as client:
        yield client, session
    session.close()
    app.dependency_overrides.clear()


@pytest.mark.integration
def test_graph_query_no_hits_returns_empty(graph_query_client) -> None:
    client, session = graph_query_client
    job = CrawlJob(
        seed_url="https://gq-empty.example/",
        normalized_seed_url="https://gq-empty.example/",
        status="completed",
    )
    session.add(job)
    session.commit()

    p = Page(
        crawl_job_id=job.id,
        url="https://gq-empty.example/p",
        normalized_url="https://gq-empty.example/p",
        domain="gq-empty.example",
        title="No match terms",
        extracted_text="xyzzy alpha bravo",
        status_code=200,
        depth=0,
    )
    session.add(p)
    session.commit()
    index_page(session, p.id)
    session.commit()

    r = client.get("/graph/query", params={"q": "zebrazonmissingtoken"})
    assert r.status_code == 200
    body = r.json()
    assert body["selected_job"] is None
    assert body["nodes"] == []
    assert body["edges"] == []
    assert body["message"]


@pytest.mark.integration
def test_graph_query_auto_selects_job_by_total_bm25(graph_query_client) -> None:
    client, session = graph_query_client
    token = "uniquetermgraphqueryselectz"

    job_lo = CrawlJob(
        seed_url="https://gq-lo.example/",
        normalized_seed_url="https://gq-lo.example/",
        status="completed",
    )
    job_hi = CrawlJob(
        seed_url="https://gq-hi.example/",
        normalized_seed_url="https://gq-hi.example/",
        status="completed",
    )
    session.add_all([job_lo, job_hi])
    session.commit()

    p_lo = Page(
        crawl_job_id=job_lo.id,
        url="https://gq-lo.example/one",
        normalized_url="https://gq-lo.example/one",
        domain="gq-lo.example",
        title="Lo",
        extracted_text=f"intro {token} only one hit here",
        status_code=200,
        depth=0,
    )
    p_hi_a = Page(
        crawl_job_id=job_hi.id,
        url="https://gq-hi.example/a",
        normalized_url="https://gq-hi.example/a",
        domain="gq-hi.example",
        title="HiA",
        extracted_text=f"first paragraph {token} alpha beta gamma",
        status_code=200,
        depth=0,
    )
    p_hi_b = Page(
        crawl_job_id=job_hi.id,
        url="https://gq-hi.example/b",
        normalized_url="https://gq-hi.example/b",
        domain="gq-hi.example",
        title="HiB",
        extracted_text=f"second paragraph {token} delta epsilon",
        status_code=200,
        depth=0,
    )
    session.add_all([p_lo, p_hi_a, p_hi_b])
    session.commit()
    for pid in (p_lo.id, p_hi_a.id, p_hi_b.id):
        index_page(session, pid)
    session.commit()

    r = client.get("/graph/query", params={"q": token, "max_seed_pages": 5, "radius": 0, "max_nodes": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["selected_job"] is not None
    assert body["selected_job"]["crawl_job_id"] == job_hi.id
    assert body["selected_job"]["selection_mode"] == "auto"
    assert body["selected_job"]["hit_count"] == 2
    roles = {n["page_id"]: n["role"] for n in body["nodes"]}
    assert roles.get(p_hi_a.id) == "query_match"
    assert roles.get(p_hi_b.id) == "query_match"


@pytest.mark.integration
def test_graph_query_near_duplicate_does_not_expand(graph_query_client) -> None:
    client, session = graph_query_client
    token = "uniquetermgraphqueryneardupx"

    job = CrawlJob(
        seed_url="https://gq-nd.example/",
        normalized_seed_url="https://gq-nd.example/",
        status="completed",
    )
    session.add(job)
    session.commit()

    p_a = Page(
        crawl_job_id=job.id,
        url="https://gq-nd.example/a",
        normalized_url="https://gq-nd.example/a",
        domain="gq-nd.example",
        title="A",
        extracted_text=f"seed page {token} only here",
        status_code=200,
        depth=0,
    )
    p_b = Page(
        crawl_job_id=job.id,
        url="https://gq-nd.example/b",
        normalized_url="https://gq-nd.example/b",
        domain="gq-nd.example",
        title="B",
        extracted_text="bridge page no query token",
        status_code=200,
        depth=1,
    )
    p_c = Page(
        crawl_job_id=job.id,
        url="https://gq-nd.example/c",
        normalized_url="https://gq-nd.example/c",
        domain="gq-nd.example",
        title="C",
        extracted_text="dup target no query token",
        status_code=200,
        depth=1,
    )
    session.add_all([p_a, p_b, p_c])
    session.flush()
    session.add_all(
        [
            PageGraphEdge(
                crawl_job_id=job.id,
                source_page_id=p_a.id,
                target_page_id=p_b.id,
                edge_type="link",
                weight=1.0,
            ),
            PageGraphEdge(
                crawl_job_id=job.id,
                source_page_id=p_b.id,
                target_page_id=p_c.id,
                edge_type="near_duplicate",
                weight=0.99,
            ),
        ],
    )
    session.commit()
    for pid in (p_a.id, p_b.id, p_c.id):
        index_page(session, pid)
    session.commit()

    r = client.get(
        "/graph/query",
        params={"q": token, "max_seed_pages": 1, "radius": 3, "max_nodes": 50},
    )
    assert r.status_code == 200, r.text
    ids = {n["page_id"] for n in r.json()["nodes"]}
    assert p_a.id in ids and p_b.id in ids
    assert p_c.id not in ids


@pytest.mark.integration
def test_graph_query_duplicate_role_when_reached_via_links(graph_query_client) -> None:
    client, session = graph_query_client
    token = "uniquetermgraphqueryduprolez"

    job = CrawlJob(
        seed_url="https://gq-dup.example/",
        normalized_seed_url="https://gq-dup.example/",
        status="completed",
    )
    session.add(job)
    session.commit()

    p_a = Page(
        crawl_job_id=job.id,
        url="https://gq-dup.example/a",
        normalized_url="https://gq-dup.example/a",
        domain="gq-dup.example",
        title="A",
        extracted_text=f"seed {token}",
        status_code=200,
        depth=0,
    )
    p_b = Page(
        crawl_job_id=job.id,
        url="https://gq-dup.example/b",
        normalized_url="https://gq-dup.example/b",
        domain="gq-dup.example",
        title="B",
        extracted_text="middle",
        status_code=200,
        depth=1,
    )
    p_d = Page(
        crawl_job_id=job.id,
        url="https://gq-dup.example/d",
        normalized_url="https://gq-dup.example/d",
        domain="gq-dup.example",
        title="D",
        extracted_text="leaf",
        status_code=200,
        depth=2,
    )
    session.add_all([p_a, p_b, p_d])
    session.flush()
    session.add_all(
        [
            PageGraphEdge(
                crawl_job_id=job.id,
                source_page_id=p_a.id,
                target_page_id=p_b.id,
                edge_type="link",
                weight=1.0,
            ),
            PageGraphEdge(
                crawl_job_id=job.id,
                source_page_id=p_b.id,
                target_page_id=p_d.id,
                edge_type="link",
                weight=1.0,
            ),
            PageGraphEdge(
                crawl_job_id=job.id,
                source_page_id=p_a.id,
                target_page_id=p_d.id,
                edge_type="near_duplicate",
                weight=0.95,
            ),
        ],
    )
    session.commit()
    for pid in (p_a.id, p_b.id, p_d.id):
        index_page(session, pid)
    session.commit()

    r = client.get(
        "/graph/query",
        params={"q": token, "max_seed_pages": 1, "radius": 3, "max_nodes": 50},
    )
    assert r.status_code == 200, r.text
    roles = {n["page_id"]: n["role"] for n in r.json()["nodes"]}
    assert roles[p_a.id] == "query_match"
    assert roles[p_d.id] == "duplicate"


@pytest.mark.integration
def test_graph_query_explicit_job_id(graph_query_client) -> None:
    client, session = graph_query_client
    token = "uniquetermgraphqueryexplicitz"

    job = CrawlJob(
        seed_url="https://gq-ex.example/",
        normalized_seed_url="https://gq-ex.example/",
        status="completed",
    )
    session.add(job)
    session.commit()

    p = Page(
        crawl_job_id=job.id,
        url="https://gq-ex.example/p",
        normalized_url="https://gq-ex.example/p",
        domain="gq-ex.example",
        title="P",
        extracted_text=f"content {token}",
        status_code=200,
        depth=0,
    )
    session.add(p)
    session.commit()
    index_page(session, p.id)
    session.commit()

    r = client.get("/graph/query", params={"q": token, "job_id": job.id, "radius": 0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["selected_job"]["crawl_job_id"] == job.id
    assert body["selected_job"]["selection_mode"] == "explicit"
    assert body["nodes"]


@pytest.mark.integration
def test_graph_query_max_nodes_caps_seeds(graph_query_client) -> None:
    client, session = graph_query_client
    token = "uniquetermgraphquerycapseedz"

    job = CrawlJob(
        seed_url="https://gq-cap.example/",
        normalized_seed_url="https://gq-cap.example/",
        status="completed",
    )
    session.add(job)
    session.commit()

    pages = [
        Page(
            crawl_job_id=job.id,
            url=f"https://gq-cap.example/{i}",
            normalized_url=f"https://gq-cap.example/{i}",
            domain="gq-cap.example",
            title=f"T{i}",
            extracted_text=f"{token} page {i}",
            status_code=200,
            depth=0,
        )
        for i in range(3)
    ]
    session.add_all(pages)
    session.commit()
    for p in pages:
        index_page(session, p.id)
    session.commit()

    r = client.get(
        "/graph/query",
        params={"q": token, "max_seed_pages": 10, "radius": 0, "max_nodes": 2},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["seed_page_ids"]) == 2
    assert len(r.json()["nodes"]) == 2
