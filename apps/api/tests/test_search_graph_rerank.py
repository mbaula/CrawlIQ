"""Tests for graph-enhanced search reranking (Issue 54)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import Settings
from db.session import get_db
from db.url import sync_engine_url
from main import app
from models.domain import CrawlJob, Page, PageGraphEdge, PageGraphMetric
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


def test_graph_enhanced_requires_job_id_422(client_mock_search_db) -> None:
    client, _ = client_mock_search_db
    r = client.get("/search?q=hello&graph_enhanced=true")
    assert r.status_code == 422
    assert "job_id" in str(r.json().get("detail", "")).lower()


@pytest.mark.integration
def test_graph_enhanced_neighbor_only_and_explanation(test_database_url: str) -> None:
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
        with SessionLocal() as session:
            job = CrawlJob(
                seed_url="https://ge54.example/",
                normalized_seed_url="https://ge54.example/",
                status="completed",
            )
            session.add(job)
            session.flush()

            p_seed = Page(
                crawl_job_id=job.id,
                url="https://ge54.example/seed",
                normalized_url="https://ge54.example/seed",
                domain="ge54.example",
                title="Seed",
                extracted_text="unique ge54seedmarker alpha bravo charlie",
                depth=0,
            )
            p_weak = Page(
                crawl_job_id=job.id,
                url="https://ge54.example/weak",
                normalized_url="https://ge54.example/weak",
                domain="ge54.example",
                title="Weak",
                extracted_text="ge54seedmarker only",
                depth=0,
            )
            p_neighbor = Page(
                crawl_job_id=job.id,
                url="https://ge54.example/neighbor",
                normalized_url="https://ge54.example/neighbor",
                domain="ge54.example",
                title="NeighborOnly",
                extracted_text="no query tokens here just filler text",
                depth=0,
            )
            session.add_all([p_seed, p_weak, p_neighbor])
            session.flush()

            session.add(
                PageGraphEdge(
                    crawl_job_id=job.id,
                    source_page_id=p_seed.id,
                    target_page_id=p_neighbor.id,
                    edge_type="link",
                    weight=5.0,
                    evidence={"source": "direct_internal_link"},
                ),
            )
            session.add(
                PageGraphMetric(
                    crawl_job_id=job.id,
                    page_id=p_seed.id,
                    pagerank=0.9,
                    in_degree=1,
                    out_degree=1,
                ),
            )
            session.add(
                PageGraphMetric(
                    crawl_job_id=job.id,
                    page_id=p_neighbor.id,
                    pagerank=0.05,
                    in_degree=1,
                    out_degree=0,
                ),
            )
            session.commit()

            for pid in (p_seed.id, p_weak.id, p_neighbor.id):
                index_page(session, pid)
            session.commit()

            job_id = job.id
            neighbor_id = p_neighbor.id

        with TestClient(app) as client:
            r_bm25 = client.get(
                f"/search?q=ge54seedmarker&job_id={job_id}&limit=5",
            )
            assert r_bm25.status_code == 200
            bm25_ids = [h["page_id"] for h in r_bm25.json()["results"]]
            assert neighbor_id not in bm25_ids

            r_graph = client.get(
                f"/search?q=ge54seedmarker&job_id={job_id}&limit=5&graph_enhanced=true",
            )
            assert r_graph.status_code == 200
            body = r_graph.json()
            graph_ids = [h["page_id"] for h in body["results"]]
            assert neighbor_id in graph_ids
            hit_nb = next(h for h in body["results"] if h["page_id"] == neighbor_id)
            assert hit_nb["score_components"] is not None
            assert hit_nb["score_components"]["bm25_raw"] == 0.0
            assert hit_nb["score_explanation"]
            assert "final=" in hit_nb["score_explanation"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_graph_enhanced_duplicate_penalty_changes_order(test_database_url: str) -> None:
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
        with SessionLocal() as session:
            job = CrawlJob(
                seed_url="https://dup54.example/",
                normalized_seed_url="https://dup54.example/",
                status="completed",
            )
            session.add(job)
            session.flush()

            p_a = Page(
                crawl_job_id=job.id,
                url="https://dup54.example/a",
                normalized_url="https://dup54.example/a",
                domain="dup54.example",
                title="A",
                extracted_text="dup54uniqueword one extra",
                content_hash="samehash123",
                depth=0,
            )
            p_b = Page(
                crawl_job_id=job.id,
                url="https://dup54.example/b",
                normalized_url="https://dup54.example/b",
                domain="dup54.example",
                title="B",
                extracted_text="dup54uniqueword two",
                content_hash="samehash123",
                depth=0,
            )
            session.add_all([p_a, p_b])
            session.flush()
            session.add(
                PageGraphEdge(
                    crawl_job_id=job.id,
                    source_page_id=p_a.id,
                    target_page_id=p_b.id,
                    edge_type="near_duplicate",
                    weight=1.0,
                    evidence={"kind": "content_hash_match"},
                ),
            )
            session.commit()
            for pid in (p_a.id, p_b.id):
                index_page(session, pid)
            session.commit()
            job_id = job.id
            a_id, b_id = p_a.id, p_b.id

        with TestClient(app) as client:
            r = client.get(
                f"/search?q=dup54uniqueword&job_id={job_id}&limit=5&graph_enhanced=true",
            )
            assert r.status_code == 200
            results = r.json()["results"]
            assert len(results) >= 2
            first = results[0]["page_id"]
            second = results[1]["page_id"]
            assert {first, second} == {a_id, b_id}
            dup_hit = next(h for h in results if h["page_id"] == b_id)
            assert dup_hit["score_components"]["duplicate_penalty_raw"] >= 1.0
    finally:
        app.dependency_overrides.clear()


def test_settings_rejects_seed_above_max() -> None:
    with pytest.raises((ValueError, ValidationError), match="graph_rerank"):
        Settings(
            graph_rerank_seed_limit=500,
            graph_rerank_max_candidates=100,
        )
