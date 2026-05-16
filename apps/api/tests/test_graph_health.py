"""Tests for ``GET /graph/health``."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.session import get_db
from db.url import sync_engine_url
from main import app
from models.domain import CrawlJob, Page, PageGraphCluster, PageGraphEdge, PageGraphMetric


@pytest.mark.integration
def test_graph_health_no_job_id_returns_placeholder(test_database_url: str) -> None:
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
        with TestClient(app) as client:
            r = client.get("/graph/health")
            assert r.status_code == 200
            body = r.json()
            assert body["job_id"] is None
            assert body["summary"] is None
            assert "job_id" in (body.get("message") or "").lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_graph_health_job_summarizes_precomputed_data(test_database_url: str) -> None:
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
                seed_url="https://gh.example/",
                normalized_seed_url="https://gh.example/",
                status="completed",
            )
            session.add(job)
            session.flush()
            p1 = Page(
                crawl_job_id=job.id,
                url="https://gh.example/a",
                normalized_url="https://gh.example/a",
                domain="gh.example",
                title="Alpha",
                depth=0,
                fetched_at=datetime.now(timezone.utc),
            )
            p2 = Page(
                crawl_job_id=job.id,
                url="https://gh.example/b",
                normalized_url="https://gh.example/b",
                domain="gh.example",
                title="Beta",
                depth=0,
                fetched_at=datetime.now(timezone.utc),
            )
            session.add_all([p1, p2])
            session.flush()
            session.add(
                PageGraphEdge(
                    crawl_job_id=job.id,
                    source_page_id=p1.id,
                    target_page_id=p2.id,
                    edge_type="link",
                    weight=1.0,
                    evidence={"source": "direct_internal_link"},
                ),
            )
            session.add_all(
                [
                    PageGraphMetric(
                        crawl_job_id=job.id,
                        page_id=p1.id,
                        pagerank=0.5,
                        in_degree=0,
                        out_degree=1,
                    ),
                    PageGraphMetric(
                        crawl_job_id=job.id,
                        page_id=p2.id,
                        pagerank=0.2,
                        in_degree=1,
                        out_degree=0,
                    ),
                ],
            )
            session.add_all(
                [
                    PageGraphCluster(crawl_job_id=job.id, page_id=p1.id, cluster_id=1, cluster_label="c1"),
                    PageGraphCluster(crawl_job_id=job.id, page_id=p2.id, cluster_id=1, cluster_label="c1"),
                ],
            )
            session.add(
                PageGraphEdge(
                    crawl_job_id=job.id,
                    source_page_id=p1.id,
                    target_page_id=p2.id,
                    edge_type="near_duplicate",
                    weight=1.0,
                    evidence={"kind": "content_hash_match", "content_hash": "x"},
                ),
            )
            session.commit()
            job_id = job.id
            p1_id = p1.id

        with TestClient(app) as client:
            r = client.get("/graph/health", params={"job_id": job_id})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["job_id"] == job_id
            assert body["summary"]["page_count"] == 2
            assert body["summary"]["edge_count"] == 2
            assert body["summary"]["metrics_count"] == 2
            assert body["summary"]["distinct_cluster_ids"] == 1
            assert body["summary"]["duplicate_cluster_count"] >= 1
            assert len(body["hub_pages"]) >= 1
            assert body["hub_pages"][0]["page_id"] == p1_id
            assert len(body["duplicate_clusters"]) >= 1
            dc = next(d for d in body["duplicate_clusters"] if d["canonical_page_id"] == p1_id)
            assert dc["duplicate_count"] >= 1
            assert len(dc["duplicates"]) >= 1
    finally:
        app.dependency_overrides.clear()
