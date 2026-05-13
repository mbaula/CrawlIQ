"""Tests for URL hierarchy graph edges."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from crawliq_core.url_normalize import normalize_url
from db.url import sync_engine_url
from models.domain import CrawlJob, Page, PageGraphEdge
from services.page_graph_url_hierarchy_edges import (
    _hierarchy_evidence_json,
    _immediate_parent_normalized_url,
    generate_url_hierarchy_edges_for_job,
)


def test_immediate_parent_url_matches_canonical_pages() -> None:
    child = normalize_url("https://uh.example/docs/tutorial/deps")
    parent = _immediate_parent_normalized_url(child)
    assert parent == normalize_url("https://uh.example/docs/tutorial")


def test_immediate_parent_single_segment_points_at_host_root() -> None:
    child = normalize_url("https://uh.example/docs")
    parent = _immediate_parent_normalized_url(child)
    assert parent == normalize_url("https://uh.example/")


def test_immediate_parent_host_only_no_parent() -> None:
    assert _immediate_parent_normalized_url(normalize_url("https://uh.example/")) is None


def test_hierarchy_evidence_json_sorted_keys() -> None:
    p = normalize_url("https://uh.example/docs")
    c = normalize_url("https://uh.example/docs/tutorial")
    s = _hierarchy_evidence_json(p, c)
    assert s == json.dumps(json.loads(s), sort_keys=True)
    assert json.loads(s) == {"child_path": "/docs/tutorial", "parent_path": "/docs"}


@pytest.mark.integration
def test_url_hierarchy_chain_three_pages(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://chain.example/",
            normalized_seed_url=normalize_url("https://chain.example/"),
            status="completed",
        )
        session.add(job)
        session.flush()
        u1 = normalize_url("https://chain.example/docs")
        u2 = normalize_url("https://chain.example/docs/tutorial")
        u3 = normalize_url("https://chain.example/docs/tutorial/deps")
        p1 = Page(
            crawl_job_id=job.id,
            url=u1,
            normalized_url=u1,
            domain="chain.example",
            depth=0,
        )
        p2 = Page(
            crawl_job_id=job.id,
            url=u2,
            normalized_url=u2,
            domain="chain.example",
            depth=1,
        )
        p3 = Page(
            crawl_job_id=job.id,
            url=u3,
            normalized_url=u3,
            domain="chain.example",
            depth=2,
        )
        session.add_all([p1, p2, p3])
        session.commit()
        job_id = job.id

    with SessionLocal() as session:
        n = generate_url_hierarchy_edges_for_job(session, job_id)
        session.commit()
        assert n == 2

        n2 = generate_url_hierarchy_edges_for_job(session, job_id)
        session.commit()
        assert n2 == 0

        total = session.scalar(
            select(func.count()).select_from(PageGraphEdge).where(
                PageGraphEdge.crawl_job_id == job_id,
                PageGraphEdge.edge_type == "url_hierarchy",
            ),
        )
        assert int(total or 0) == 2


@pytest.mark.integration
def test_url_hierarchy_missing_intermediate_no_skip_level_edge(test_database_url: str) -> None:
    """No edge to a synthetic parent; deep page alone yields zero hierarchy edges."""
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://skip.example/",
            normalized_seed_url=normalize_url("https://skip.example/"),
            status="completed",
        )
        session.add(job)
        session.flush()
        leaf = normalize_url("https://skip.example/docs/tutorial/deps")
        session.add(
            Page(
                crawl_job_id=job.id,
                url=leaf,
                normalized_url=leaf,
                domain="skip.example",
                depth=0,
            ),
        )
        session.commit()
        job_id = job.id

    with SessionLocal() as session:
        n = generate_url_hierarchy_edges_for_job(session, job_id)
        session.commit()
        assert n == 0


@pytest.mark.integration
def test_url_hierarchy_different_hosts_no_cross_edges(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://a-cross.example/p",
            normalized_seed_url=normalize_url("https://a-cross.example/p"),
            status="completed",
        )
        session.add(job)
        session.flush()
        ua = normalize_url("https://a-cross.example/docs/x")
        ub = normalize_url("https://b-other.example/docs/x/y")
        session.add_all(
            [
                Page(
                    crawl_job_id=job.id,
                    url=ua,
                    normalized_url=ua,
                    domain="a-cross.example",
                    depth=0,
                ),
                Page(
                    crawl_job_id=job.id,
                    url=ub,
                    normalized_url=ub,
                    domain="b-other.example",
                    depth=1,
                ),
            ],
        )
        session.commit()
        job_id = job.id

    with SessionLocal() as session:
        n = generate_url_hierarchy_edges_for_job(session, job_id)
        session.commit()
        assert n == 0


@pytest.mark.integration
def test_url_hierarchy_root_and_one_segment(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://root.example/",
            normalized_seed_url=normalize_url("https://root.example/"),
            status="completed",
        )
        session.add(job)
        session.flush()
        root = normalize_url("https://root.example/")
        doc = normalize_url("https://root.example/docs")
        pr = Page(
            crawl_job_id=job.id,
            url=root,
            normalized_url=root,
            domain="root.example",
            depth=0,
        )
        pd = Page(
            crawl_job_id=job.id,
            url=doc,
            normalized_url=doc,
            domain="root.example",
            depth=1,
        )
        session.add_all([pr, pd])
        session.commit()
        job_id = job.id

    with SessionLocal() as session:
        n = generate_url_hierarchy_edges_for_job(session, job_id)
        session.commit()
        assert n == 1
        row = session.scalar(
            select(PageGraphEdge).where(
                PageGraphEdge.crawl_job_id == job_id,
                PageGraphEdge.edge_type == "url_hierarchy",
            ),
        )
        assert row is not None
        assert row.weight == 0.9
        assert row.source_page_id != row.target_page_id
