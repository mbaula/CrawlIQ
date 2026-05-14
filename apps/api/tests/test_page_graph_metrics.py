"""Tests for ``page_graph_metrics`` / ``page_graph_clusters`` computation."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from config import Settings
from crawliq_core.url_normalize import normalize_url
from db.url import sync_engine_url
from models.domain import CrawlJob, Page, PageGraphCluster, PageGraphEdge, PageGraphMetric
from services.page_graph_metrics import (
    _pagerank_directed_weighted,
    _union_find,
    compute_graph_metrics_for_job,
)


def test_pagerank_chain_favors_middle_node() -> None:
    nodes = [1, 2, 3]
    merged = {1: {2: 1.0}, 2: {3: 1.0}}
    out_sum = {1: 1.0, 2: 1.0, 3: 0.0}
    pr, it = _pagerank_directed_weighted(nodes, merged, out_sum)
    assert it >= 1
    assert pr[2] > pr[1]
    assert abs(sum(pr.values()) - 1.0) < 1e-9
    assert all(v > 0 for v in pr.values())


def test_union_find_min_id_root() -> None:
    roots = _union_find([10, 20, 30], [(10, 20), (20, 30)])
    assert roots[10] == roots[20] == roots[30] == 10


@pytest.mark.integration
def test_graph_metrics_chain_and_isolate(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://gm.example/",
            normalized_seed_url=normalize_url("https://gm.example/"),
            status="completed",
        )
        session.add(job)
        session.flush()
        base = "https://gm.example"
        pa = Page(
            crawl_job_id=job.id,
            url=f"{base}/a",
            normalized_url=normalize_url(f"{base}/a"),
            domain="gm.example",
            title="a",
            depth=0,
        )
        pb = Page(
            crawl_job_id=job.id,
            url=f"{base}/b",
            normalized_url=normalize_url(f"{base}/b"),
            domain="gm.example",
            title="b",
            depth=0,
        )
        pc = Page(
            crawl_job_id=job.id,
            url=f"{base}/c",
            normalized_url=normalize_url(f"{base}/c"),
            domain="gm.example",
            title="c",
            depth=0,
        )
        pd = Page(
            crawl_job_id=job.id,
            url=f"{base}/d",
            normalized_url=normalize_url(f"{base}/d"),
            domain="gm.example",
            title="d",
            depth=0,
        )
        session.add_all([pa, pb, pc, pd])
        session.flush()
        a, b, c, d = pa.id, pb.id, pc.id, pd.id
        session.add_all(
            [
                PageGraphEdge(
                    crawl_job_id=job.id,
                    source_page_id=a,
                    target_page_id=b,
                    edge_type="link",
                    weight=1.0,
                ),
                PageGraphEdge(
                    crawl_job_id=job.id,
                    source_page_id=b,
                    target_page_id=c,
                    edge_type="link",
                    weight=1.0,
                ),
            ],
        )
        session.commit()
        job_id = job.id

    cfg = Settings(database_url="", redis_url="", graph_metrics_betweenness_max_pages=500)

    with SessionLocal() as session:
        r1 = compute_graph_metrics_for_job(session, job_id, settings=cfg)
        session.commit()
        assert r1.pages_count == 4
        assert r1.edges_used == 2
        assert r1.weak_components_count == 2
        assert r1.betweenness_computed is True

        m_b = session.scalar(select(PageGraphMetric).where(PageGraphMetric.page_id == b))
        m_a = session.scalar(select(PageGraphMetric).where(PageGraphMetric.page_id == a))
        m_c = session.scalar(select(PageGraphMetric).where(PageGraphMetric.page_id == c))
        assert m_b is not None and m_a is not None and m_c is not None
        assert m_b.pagerank is not None and m_b.pagerank > m_a.pagerank
        prs = session.scalars(
            select(PageGraphMetric.pagerank).where(PageGraphMetric.crawl_job_id == job_id),
        ).all()
        assert abs(sum(float(x) for x in prs if x is not None) - 1.0) < 1e-6
        assert m_a.in_degree == 0 and m_a.out_degree == 1
        assert m_b.in_degree == 1 and m_b.out_degree == 1
        assert m_c.in_degree == 1 and m_c.out_degree == 0

        for pid, exp in [(a, a), (b, a), (c, a), (d, d)]:
            cl = session.scalar(select(PageGraphCluster).where(PageGraphCluster.page_id == pid))
            assert cl is not None
            assert cl.cluster_id == exp

        r2 = compute_graph_metrics_for_job(session, job_id, settings=cfg)
        session.commit()
        m_b2 = session.scalar(select(PageGraphMetric).where(PageGraphMetric.page_id == b))
        assert m_b2 is not None and m_b2.pagerank == pytest.approx(m_b.pagerank, rel=0, abs=1e-9)


@pytest.mark.integration
def test_graph_metrics_skips_betweenness_above_cap(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://gmcap.example/",
            normalized_seed_url=normalize_url("https://gmcap.example/"),
            status="completed",
        )
        session.add(job)
        session.flush()
        pages = []
        for i in range(4):
            p = Page(
                crawl_job_id=job.id,
                url=f"https://gmcap.example/p{i}",
                normalized_url=normalize_url(f"https://gmcap.example/p{i}"),
                domain="gmcap.example",
                title="t",
                depth=0,
            )
            pages.append(p)
        session.add_all(pages)
        session.commit()
        job_id = job.id

    cfg = Settings(database_url="", redis_url="", graph_metrics_betweenness_max_pages=2)

    with SessionLocal() as session:
        r = compute_graph_metrics_for_job(session, job_id, settings=cfg)
        session.commit()
        assert r.pages_count == 4
        assert r.betweenness_computed is False
        null_bt = session.scalar(
            select(func.count()).select_from(PageGraphMetric).where(
                PageGraphMetric.crawl_job_id == job_id,
                PageGraphMetric.betweenness.is_(None),
            ),
        )
        assert int(null_bt or 0) == 4
