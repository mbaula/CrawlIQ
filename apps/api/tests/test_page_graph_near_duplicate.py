"""Tests for ``near_duplicate`` graph edges (content hash + high similarity)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from config import Settings
from crawliq_core.url_normalize import normalize_url
from db.url import sync_engine_url
from models.domain import CrawlJob, InvertedIndex, Page, PageGraphEdge, PageLink, Term
from services.page_graph_near_duplicate import (
    _pick_canonical,
    generate_near_duplicate_edges_for_job,
)


def _stub_page(
    *,
    pid: int,
    url: str,
    title: str | None = "T",
    fetched: datetime | None = None,
    chash: str | None = "h",
) -> Page:
    nu = normalize_url(url)
    p = Page(
        crawl_job_id=1,
        url=url,
        normalized_url=nu,
        domain="nd.example",
        title=title,
        depth=0,
        content_hash=chash,
    )
    object.__setattr__(p, "id", pid)
    if fetched is not None:
        p.fetched_at = fetched
    return p


def test_canonical_prefers_shorter_normalized_url() -> None:
    long_p = _stub_page(pid=1, url="https://nd.example/aaaa")
    short_p = _stub_page(pid=2, url="https://nd.example/a")
    c = _pick_canonical([long_p, short_p], {1: 0, 2: 0})
    assert c.id == 2


def test_canonical_prefers_higher_inbound_when_url_len_equal() -> None:
    p1 = _stub_page(pid=1, url="https://nd.example/p1")
    p2 = _stub_page(pid=2, url="https://nd.example/p2")
    c = _pick_canonical([p1, p2], {1: 0, 2: 5})
    assert c.id == 2


def test_canonical_prefers_nonempty_title_then_longer_title() -> None:
    p1 = _stub_page(pid=1, url="https://nd.example/x", title=None)
    p2 = _stub_page(pid=2, url="https://nd.example/y", title="ab")
    c = _pick_canonical([p1, p2], {1: 0, 2: 0})
    assert c.id == 2


def test_canonical_lexicographic_title_then_fetched_then_id() -> None:
    t0 = datetime(2026, 1, 2, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    p1 = _stub_page(pid=10, url="https://nd.example/z", title="b", fetched=t0)
    p2 = _stub_page(pid=20, url="https://nd.example/z", title="a", fetched=t0)
    # Same len url, inbound, title length; lexicographic title: "a" wins
    c = _pick_canonical([p1, p2], {10: 1, 20: 1})
    assert c.id == 20

    p3 = _stub_page(pid=3, url="https://nd.example/q", title="same", fetched=t0)
    p4 = _stub_page(pid=4, url="https://nd.example/q", title="same", fetched=t1)
    c2 = _pick_canonical([p3, p4], {3: 0, 4: 0})
    assert c2.id == 4  # earlier fetched_at

    p5 = _stub_page(pid=5, url="https://nd.example/r", title="x", fetched=t0)
    p6 = _stub_page(pid=6, url="https://nd.example/r", title="x", fetched=t0)
    c3 = _pick_canonical([p5, p6], {5: 0, 6: 0})
    assert c3.id == 5  # smaller id


@pytest.mark.integration
def test_near_duplicate_exact_hash_group(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    h = "deadbeef" * 4

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://nd.example/",
            normalized_seed_url=normalize_url("https://nd.example/"),
            status="completed",
        )
        session.add(job)
        session.flush()
        p_short = Page(
            crawl_job_id=job.id,
            url="https://nd.example/s",
            normalized_url=normalize_url("https://nd.example/s"),
            domain="nd.example",
            title="t",
            depth=0,
            content_hash=h,
        )
        p_long = Page(
            crawl_job_id=job.id,
            url="https://nd.example/loooooong",
            normalized_url=normalize_url("https://nd.example/loooooong"),
            domain="nd.example",
            title="t",
            depth=0,
            content_hash=h,
        )
        p_other = Page(
            crawl_job_id=job.id,
            url="https://nd.example/otherhash",
            normalized_url=normalize_url("https://nd.example/otherhash"),
            domain="nd.example",
            title="t",
            depth=0,
            content_hash="cafe" * 8,
        )
        session.add_all([p_short, p_long, p_other])
        session.commit()
        job_id = job.id
        short_id, long_id = p_short.id, p_long.id

    cfg = Settings(database_url="", redis_url="", graph_near_duplicate_min_score=0.99)

    with SessionLocal() as session:
        n = generate_near_duplicate_edges_for_job(session, job_id, settings=cfg)
        session.commit()
        assert n == 1

        row = session.scalar(
            select(PageGraphEdge).where(
                PageGraphEdge.crawl_job_id == job_id,
                PageGraphEdge.edge_type == "near_duplicate",
            ),
        )
        assert row is not None
        assert row.source_page_id == short_id
        assert row.target_page_id == long_id
        assert row.weight == 1.0
        assert row.evidence == {"kind": "content_hash_match", "content_hash": h}

        n2 = generate_near_duplicate_edges_for_job(session, job_id, settings=cfg)
        session.commit()
        assert n2 == 0


@pytest.mark.integration
def test_near_duplicate_inbound_tie_breaks_canonical(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    h = "ab" * 32

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://inb.example/",
            normalized_seed_url=normalize_url("https://inb.example/"),
            status="completed",
        )
        session.add(job)
        session.flush()
        p1 = Page(
            crawl_job_id=job.id,
            url="https://inb.example/p1",
            normalized_url=normalize_url("https://inb.example/p1"),
            domain="inb.example",
            title="t",
            depth=0,
            content_hash=h,
        )
        p2 = Page(
            crawl_job_id=job.id,
            url="https://inb.example/p2",
            normalized_url=normalize_url("https://inb.example/p2"),
            domain="inb.example",
            title="t",
            depth=0,
            content_hash=h,
        )
        session.add_all([p1, p2])
        session.flush()
        hub = Page(
            crawl_job_id=job.id,
            url="https://inb.example/hub",
            normalized_url=normalize_url("https://inb.example/hub"),
            domain="inb.example",
            title="h",
            depth=0,
            content_hash="99" * 32,
        )
        session.add(hub)
        session.flush()
        session.add(
            PageLink(
                crawl_job_id=job.id,
                source_page_id=hub.id,
                target_normalized_url=p2.normalized_url,
                depth=1,
            ),
        )
        session.commit()
        job_id = job.id
        p1_id, p2_id = p1.id, p2.id

    cfg = Settings(database_url="", redis_url="", graph_near_duplicate_min_score=0.99)

    with SessionLocal() as session:
        n = generate_near_duplicate_edges_for_job(session, job_id, settings=cfg)
        session.commit()
        assert n == 1
        row = session.scalar(
            select(PageGraphEdge).where(
                PageGraphEdge.crawl_job_id == job_id,
                PageGraphEdge.edge_type == "near_duplicate",
            ),
        )
        assert row is not None
        assert row.source_page_id == p2_id
        assert row.target_page_id == p1_id


@pytest.mark.integration
def test_near_duplicate_high_similarity_different_hash(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://hsim.example/",
            normalized_seed_url=normalize_url("https://hsim.example/"),
            status="completed",
        )
        session.add(job)
        session.flush()
        t = Term(term="shared_nd_term")
        session.add(t)
        session.flush()
        u = "https://hsim.example"
        p1 = Page(
            crawl_job_id=job.id,
            url=f"{u}/a",
            normalized_url=normalize_url(f"{u}/a"),
            domain="hsim.example",
            title="t",
            depth=0,
            content_hash="11" * 32,
        )
        p2 = Page(
            crawl_job_id=job.id,
            url=f"{u}/b",
            normalized_url=normalize_url(f"{u}/b"),
            domain="hsim.example",
            title="t",
            depth=0,
            content_hash="22" * 32,
        )
        session.add_all([p1, p2])
        session.flush()
        session.add_all(
            [
                InvertedIndex(page_id=p1.id, term_id=t.id, term_frequency=5),
                InvertedIndex(page_id=p2.id, term_id=t.id, term_frequency=5),
            ],
        )
        session.commit()
        job_id = job.id
        p1_id, p2_id = p1.id, p2.id

    cfg = Settings(database_url="", redis_url="", graph_near_duplicate_min_score=0.92)

    with SessionLocal() as session:
        n = generate_near_duplicate_edges_for_job(session, job_id, settings=cfg)
        session.commit()
        assert n == 1
        row = session.scalar(
            select(PageGraphEdge).where(
                PageGraphEdge.crawl_job_id == job_id,
                PageGraphEdge.edge_type == "near_duplicate",
            ),
        )
        assert row is not None
        assert row.source_page_id == p1_id  # shorter URL
        assert row.target_page_id == p2_id
        assert row.weight == pytest.approx(1.0)
        assert row.evidence["kind"] == "high_similarity"
        assert row.evidence["shared_terms"] == ["shared_nd_term"]
        assert row.evidence["similarity"] == pytest.approx(1.0)


@pytest.mark.integration
def test_near_duplicate_no_cross_job_edges(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    h = "cc" * 32

    with SessionLocal() as session:
        j1 = CrawlJob(
            seed_url="https://cj1.example/",
            normalized_seed_url=normalize_url("https://cj1.example/"),
            status="completed",
        )
        j2 = CrawlJob(
            seed_url="https://cj2.example/",
            normalized_seed_url=normalize_url("https://cj2.example/"),
            status="completed",
        )
        session.add_all([j1, j2])
        session.flush()
        a1 = Page(
            crawl_job_id=j1.id,
            url="https://cj1.example/a",
            normalized_url=normalize_url("https://cj1.example/a"),
            domain="cj1.example",
            title="t",
            depth=0,
            content_hash=h,
        )
        a2 = Page(
            crawl_job_id=j1.id,
            url="https://cj1.example/b",
            normalized_url=normalize_url("https://cj1.example/b"),
            domain="cj1.example",
            title="t",
            depth=0,
            content_hash=h,
        )
        b1 = Page(
            crawl_job_id=j2.id,
            url="https://cj2.example/a",
            normalized_url=normalize_url("https://cj2.example/a"),
            domain="cj2.example",
            title="t",
            depth=0,
            content_hash=h,
        )
        b2 = Page(
            crawl_job_id=j2.id,
            url="https://cj2.example/b",
            normalized_url=normalize_url("https://cj2.example/b"),
            domain="cj2.example",
            title="t",
            depth=0,
            content_hash=h,
        )
        session.add_all([a1, a2, b1, b2])
        session.commit()
        j1_id, j2_id = j1.id, j2.id

    cfg = Settings(database_url="", redis_url="", graph_near_duplicate_min_score=0.99)

    with SessionLocal() as session:
        n = generate_near_duplicate_edges_for_job(session, j1_id, settings=cfg)
        session.commit()
        assert n == 1
        j2_near_dup = session.scalar(
            select(func.count()).select_from(PageGraphEdge).where(
                PageGraphEdge.crawl_job_id == j2_id,
                PageGraphEdge.edge_type == "near_duplicate",
            ),
        )
        assert int(j2_near_dup or 0) == 0
