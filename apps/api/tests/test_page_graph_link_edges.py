"""Integration tests for link-edge generation (``page_graph_edges`` from ``page_links``)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from db.url import sync_engine_url
from models.domain import CrawlJob, Page, PageGraphEdge, PageLink
from services.page_graph_link_edges import (
    LINK_EDGE_EVIDENCE_JSON,
    generate_link_edges_for_job,
)


@pytest.mark.integration
def test_link_edges_internal_and_ineligible_target_still_linked(
    test_database_url: str,
) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://g.example/",
            normalized_seed_url="https://g.example/",
            status="completed",
        )
        session.add(job)
        session.flush()

        p1 = Page(
            crawl_job_id=job.id,
            url="https://g.example/a",
            normalized_url="https://g.example/a",
            domain="g.example",
            depth=0,
        )
        p2 = Page(
            crawl_job_id=job.id,
            url="https://g.example/b",
            normalized_url="https://g.example/b",
            domain="g.example",
            depth=1,
        )
        session.add_all([p1, p2])
        session.flush()

        session.add(
            PageLink(
                crawl_job_id=job.id,
                source_page_id=p1.id,
                target_normalized_url="https://g.example/b",
                depth=1,
                is_crawl_eligible=False,
            ),
        )
        session.commit()
        job_id = job.id
        p1_id = p1.id
        p2_id = p2.id

    with SessionLocal() as session:
        n = generate_link_edges_for_job(session, job_id)
        session.commit()
        assert n == 1

        row = session.scalar(select(PageGraphEdge).where(PageGraphEdge.crawl_job_id == job_id))
        assert row is not None
        assert row.edge_type == "link"
        assert row.weight == 1.0
        assert row.source_page_id == p1_id
        assert row.target_page_id == p2_id
        assert row.evidence == {"source": "direct_internal_link"}

        n2 = generate_link_edges_for_job(session, job_id)
        session.commit()
        assert n2 == 0

        total = session.scalar(
            select(func.count()).select_from(PageGraphEdge).where(PageGraphEdge.crawl_job_id == job_id),
        )
        assert int(total or 0) == 1


@pytest.mark.integration
def test_link_edges_missing_target_no_row(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://m.example/",
            normalized_seed_url="https://m.example/",
            status="completed",
        )
        session.add(job)
        session.flush()
        p1 = Page(
            crawl_job_id=job.id,
            url="https://m.example/only",
            normalized_url="https://m.example/only",
            domain="m.example",
            depth=0,
        )
        session.add(p1)
        session.flush()
        session.add(
            PageLink(
                crawl_job_id=job.id,
                source_page_id=p1.id,
                target_normalized_url="https://m.example/not-crawled",
                depth=1,
                is_crawl_eligible=True,
            ),
        )
        job_id = job.id
        session.commit()

    with SessionLocal() as session:
        n = generate_link_edges_for_job(session, job_id)
        session.commit()
        assert n == 0


@pytest.mark.integration
def test_link_edges_skip_self_link(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        job = CrawlJob(
            seed_url="https://s.example/",
            normalized_seed_url="https://s.example/",
            status="completed",
        )
        session.add(job)
        session.flush()
        p1 = Page(
            crawl_job_id=job.id,
            url="https://s.example/self",
            normalized_url="https://s.example/self",
            domain="s.example",
            depth=0,
        )
        session.add(p1)
        session.flush()
        session.add(
            PageLink(
                crawl_job_id=job.id,
                source_page_id=p1.id,
                target_normalized_url="https://s.example/self",
                depth=0,
                is_crawl_eligible=True,
            ),
        )
        job_id = job.id
        session.commit()

    with SessionLocal() as session:
        n = generate_link_edges_for_job(session, job_id)
        session.commit()
        assert n == 0


def test_link_edge_evidence_json_is_deterministic() -> None:
    assert LINK_EDGE_EVIDENCE_JSON == '{"source": "direct_internal_link"}'
