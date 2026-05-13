"""Tests for ``content_similarity`` graph edges (TF–IDF cosine over ``inverted_index``)."""

from __future__ import annotations

import math

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from config import Settings
from crawliq_core.url_normalize import normalize_url
from db.url import sync_engine_url
from models.domain import CrawlJob, InvertedIndex, Page, PageGraphEdge, Term
from services.page_graph_content_similarity import (
    SIMILARITY_EVIDENCE_SOURCE,
    _cosine_sparse,
    _job_local_idf,
    generate_content_similarity_edges_for_job,
)


def test_job_local_idf_smoothing() -> None:
    assert _job_local_idf(n_docs=3, df=2) == math.log(4 / 3)


def test_cosine_sparse_parallel_unit_vectors() -> None:
    wp = {1: 1.0}
    wq = {1: 1.0}
    assert _cosine_sparse(wp, wq, 1.0, 1.0) == 1.0


def test_cosine_sparse_mixed_weights() -> None:
    """Match manual cosine for 2-D positive vectors."""
    wp = {1: 10.0, 2: 1.0}
    wq = {1: 1.0, 2: 10.0}
    np_ = math.sqrt(101.0)
    nq = math.sqrt(101.0)
    expected = 20.0 / (np_ * nq)
    assert abs(_cosine_sparse(wp, wq, np_, nq) - expected) < 1e-9


@pytest.mark.integration
def test_content_similarity_symmetric_high_score_and_idempotency(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://sim.example/",
            normalized_seed_url=normalize_url("https://sim.example/"),
            status="completed",
        )
        session.add(job)
        session.flush()
        ta = Term(term="alpha_sim")
        tb = Term(term="beta_only")
        session.add_all([ta, tb])
        session.flush()

        u = "https://sim.example"
        p1 = Page(
            crawl_job_id=job.id,
            url=f"{u}/p1",
            normalized_url=normalize_url(f"{u}/p1"),
            domain="sim.example",
            depth=0,
        )
        p2 = Page(
            crawl_job_id=job.id,
            url=f"{u}/p2",
            normalized_url=normalize_url(f"{u}/p2"),
            domain="sim.example",
            depth=0,
        )
        p3 = Page(
            crawl_job_id=job.id,
            url=f"{u}/p3",
            normalized_url=normalize_url(f"{u}/p3"),
            domain="sim.example",
            depth=0,
        )
        session.add_all([p1, p2, p3])
        session.flush()

        session.add_all(
            [
                InvertedIndex(page_id=p1.id, term_id=ta.id, term_frequency=10),
                InvertedIndex(page_id=p2.id, term_id=ta.id, term_frequency=10),
                InvertedIndex(page_id=p3.id, term_id=tb.id, term_frequency=10),
            ],
        )
        session.commit()
        job_id = job.id

    cfg = Settings(
        database_url="",
        redis_url="",
        graph_similarity_top_k=10,
        graph_similarity_min_score=0.15,
    )

    with SessionLocal() as session:
        n = generate_content_similarity_edges_for_job(session, job_id, settings=cfg)
        session.commit()
        assert n == 2

        n2 = generate_content_similarity_edges_for_job(session, job_id, settings=cfg)
        session.commit()
        assert n2 == 0

        rows = session.scalars(
            select(PageGraphEdge).where(
                PageGraphEdge.crawl_job_id == job_id,
                PageGraphEdge.edge_type == "content_similarity",
            ),
        ).all()
        assert len(rows) == 2
        for row in rows:
            assert row.weight == pytest.approx(1.0)
            assert row.evidence["source"] == SIMILARITY_EVIDENCE_SOURCE
            assert row.evidence["shared_terms"] == ["alpha_sim"]
            assert row.evidence["similarity"] == pytest.approx(1.0)


@pytest.mark.integration
def test_content_similarity_min_score_filters_low_cosine(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://lowcos.example/",
            normalized_seed_url=normalize_url("https://lowcos.example/"),
            status="completed",
        )
        session.add(job)
        session.flush()
        t1 = Term(term="t1_lc")
        t2 = Term(term="t2_lc")
        tg = Term(term="tg_lc")
        session.add_all([t1, t2, tg])
        session.flush()

        base = "https://lowcos.example"
        p1 = Page(
            crawl_job_id=job.id,
            url=f"{base}/a",
            normalized_url=normalize_url(f"{base}/a"),
            domain="lowcos.example",
            depth=0,
        )
        p2 = Page(
            crawl_job_id=job.id,
            url=f"{base}/b",
            normalized_url=normalize_url(f"{base}/b"),
            domain="lowcos.example",
            depth=0,
        )
        p3 = Page(
            crawl_job_id=job.id,
            url=f"{base}/c",
            normalized_url=normalize_url(f"{base}/c"),
            domain="lowcos.example",
            depth=0,
        )
        session.add_all([p1, p2, p3])
        session.flush()

        session.add_all(
            [
                InvertedIndex(page_id=p1.id, term_id=t1.id, term_frequency=10),
                InvertedIndex(page_id=p1.id, term_id=t2.id, term_frequency=1),
                InvertedIndex(page_id=p2.id, term_id=t1.id, term_frequency=1),
                InvertedIndex(page_id=p2.id, term_id=t2.id, term_frequency=10),
                InvertedIndex(page_id=p3.id, term_id=tg.id, term_frequency=1),
            ],
        )
        session.commit()
        job_id = job.id

    strict = Settings(
        database_url="",
        redis_url="",
        graph_similarity_top_k=10,
        graph_similarity_min_score=0.25,
    )
    loose = Settings(
        database_url="",
        redis_url="",
        graph_similarity_top_k=10,
        graph_similarity_min_score=0.15,
    )

    with SessionLocal() as session:
        n_strict = generate_content_similarity_edges_for_job(session, job_id, settings=strict)
        session.commit()
        assert n_strict == 0

        n_loose = generate_content_similarity_edges_for_job(session, job_id, settings=loose)
        session.commit()
        assert n_loose >= 1

        total = session.scalar(
            select(func.count()).select_from(PageGraphEdge).where(
                PageGraphEdge.crawl_job_id == job_id,
                PageGraphEdge.edge_type == "content_similarity",
            ),
        )
        assert int(total or 0) >= 1


@pytest.mark.integration
def test_content_similarity_top_k_outgoing_cap(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://topk.example/",
            normalized_seed_url=normalize_url("https://topk.example/"),
            status="completed",
        )
        session.add(job)
        session.flush()
        tx = Term(term="shared_topk")
        ty = Term(term="other_topk")
        session.add_all([tx, ty])
        session.flush()

        base = "https://topk.example"
        pages: list[Page] = []
        for i in range(4):
            p = Page(
                crawl_job_id=job.id,
                url=f"{base}/p{i}",
                normalized_url=normalize_url(f"{base}/p{i}"),
                domain="topk.example",
                depth=0,
            )
            pages.append(p)
        p4 = Page(
            crawl_job_id=job.id,
            url=f"{base}/p4",
            normalized_url=normalize_url(f"{base}/p4"),
            domain="topk.example",
            depth=0,
        )
        session.add_all([*pages, p4])
        session.flush()
        for p in pages:
            session.add(InvertedIndex(page_id=p.id, term_id=tx.id, term_frequency=1))
        session.add(InvertedIndex(page_id=p4.id, term_id=ty.id, term_frequency=1))
        session.commit()
        job_id = job.id
        hub_id = pages[0].id

    cfg = Settings(
        database_url="",
        redis_url="",
        graph_similarity_top_k=1,
        graph_similarity_min_score=0.01,
    )

    with SessionLocal() as session:
        n = generate_content_similarity_edges_for_job(session, job_id, settings=cfg)
        session.commit()
        assert n == 4

        out_from_hub = session.scalar(
            select(func.count()).select_from(PageGraphEdge).where(
                PageGraphEdge.crawl_job_id == job_id,
                PageGraphEdge.edge_type == "content_similarity",
                PageGraphEdge.source_page_id == hub_id,
            ),
        )
        assert int(out_from_hub or 0) == 1


def test_cosine_sparse_rejects_zero_norm() -> None:
    assert _cosine_sparse({1: 1.0}, {1: 1.0}, 0.0, 1.0) == 0.0
