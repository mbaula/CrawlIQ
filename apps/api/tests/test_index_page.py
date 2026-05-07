"""Unit tests for indexing a page into terms + inverted_index."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from db.url import sync_engine_url
from models.domain import CrawlJob, InvertedIndex, Page, Term
from services.index_page import index_page


def _mk_session(test_database_url: str):
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _term_row(session, term: str) -> Term:
    row = session.scalar(select(Term).where(Term.term == term))
    assert row is not None
    return row


def _tf(session, page_id: int, term: str) -> int:
    tid = _term_row(session, term).id
    row = session.scalar(
        select(InvertedIndex).where(InvertedIndex.page_id == page_id, InvertedIndex.term_id == tid),
    )
    assert row is not None
    return row.term_frequency


import pytest


@pytest.mark.integration
def test_index_page_basic_tf_df_and_token_count(test_database_url: str) -> None:
    mk = _mk_session(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://idx.example/",
            normalized_seed_url="https://idx.example/",
            status="queued",
        )
        session.add(job)
        session.commit()

        page = Page(
            crawl_job_id=job.id,
            url="https://idx.example/p1",
            normalized_url="https://idx.example/p1",
            domain="idx.example",
            title="FastAPI",
            extracted_text="FastAPI is a modern Python framework",
            status_code=200,
            depth=0,
            fetched_at=datetime.now(timezone.utc),
        )
        session.add(page)
        session.commit()
        pid = page.id

        index_page(session, pid, title_weight=3)
        session.commit()

        assert _tf(session, pid, "fastapi") == 4
        assert _tf(session, pid, "python") == 1
        assert _tf(session, pid, "framework") == 1

        assert _term_row(session, "fastapi").document_frequency == 1
        assert _term_row(session, "python").document_frequency == 1

        page2 = session.get(Page, pid)
        assert page2 is not None
        assert page2.indexed_at is not None
        assert page2.token_count == 7

        job2 = session.get(CrawlJob, job.id)
        assert job2 is not None
        assert job2.pages_indexed == 1


@pytest.mark.integration
def test_index_page_doc_frequency_across_two_pages(test_database_url: str) -> None:
    mk = _mk_session(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://idx2.example/",
            normalized_seed_url="https://idx2.example/",
            status="queued",
        )
        session.add(job)
        session.commit()

        p1 = Page(
            crawl_job_id=job.id,
            url="https://idx2.example/1",
            normalized_url="https://idx2.example/1",
            domain="idx2.example",
            title="FastAPI",
            extracted_text="Python",
            status_code=200,
            depth=0,
        )
        p2 = Page(
            crawl_job_id=job.id,
            url="https://idx2.example/2",
            normalized_url="https://idx2.example/2",
            domain="idx2.example",
            title="FastAPI",
            extracted_text="Redis",
            status_code=200,
            depth=0,
        )
        session.add(p1)
        session.add(p2)
        session.commit()

        index_page(session, p1.id)
        index_page(session, p2.id)
        session.commit()

        assert _term_row(session, "fastapi").document_frequency == 2
        assert _term_row(session, "python").document_frequency == 1
        assert _term_row(session, "redis").document_frequency == 1


@pytest.mark.integration
def test_index_page_idempotent_no_duplicate_postings(test_database_url: str) -> None:
    mk = _mk_session(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://idx3.example/",
            normalized_seed_url="https://idx3.example/",
            status="queued",
        )
        session.add(job)
        session.commit()

        page = Page(
            crawl_job_id=job.id,
            url="https://idx3.example/p",
            normalized_url="https://idx3.example/p",
            domain="idx3.example",
            title="FastAPI",
            extracted_text="Python framework",
            status_code=200,
            depth=0,
        )
        session.add(page)
        session.commit()

        index_page(session, page.id)
        session.commit()
        first_pages_indexed = session.get(CrawlJob, job.id).pages_indexed

        index_page(session, page.id)
        session.commit()

        rows = session.scalars(select(InvertedIndex).where(InvertedIndex.page_id == page.id)).all()
        assert len(rows) == len({r.term_id for r in rows})
        assert session.get(CrawlJob, job.id).pages_indexed == first_pages_indexed


@pytest.mark.integration
def test_index_page_reindex_after_content_change_updates_doc_freq(test_database_url: str) -> None:
    mk = _mk_session(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://idx4.example/",
            normalized_seed_url="https://idx4.example/",
            status="queued",
        )
        session.add(job)
        session.commit()

        page = Page(
            crawl_job_id=job.id,
            url="https://idx4.example/p",
            normalized_url="https://idx4.example/p",
            domain="idx4.example",
            title="FastAPI",
            extracted_text="Python framework",
            status_code=200,
            depth=0,
        )
        session.add(page)
        session.commit()
        pid = page.id

        index_page(session, pid)
        session.commit()

        assert _term_row(session, "python").document_frequency == 1
        assert _term_row(session, "framework").document_frequency == 1

        page2 = session.get(Page, pid)
        page2.extracted_text = "Redis queue"
        session.commit()

        index_page(session, pid)
        session.commit()

        assert _term_row(session, "python").document_frequency == 0
        assert _term_row(session, "framework").document_frequency == 0
        assert _term_row(session, "redis").document_frequency == 1
        assert _term_row(session, "queue").document_frequency == 1


@pytest.mark.integration
def test_index_page_empty_no_postings_token_count_zero(test_database_url: str) -> None:
    mk = _mk_session(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://idx5.example/",
            normalized_seed_url="https://idx5.example/",
            status="queued",
        )
        session.add(job)
        session.commit()

        page = Page(
            crawl_job_id=job.id,
            url="https://idx5.example/p",
            normalized_url="https://idx5.example/p",
            domain="idx5.example",
            title="",
            extracted_text="the and of to 123",
            status_code=200,
            depth=0,
        )
        session.add(page)
        session.commit()

        index_page(session, page.id)
        session.commit()

        assert session.scalars(select(InvertedIndex).where(InvertedIndex.page_id == page.id)).all() == []
        assert session.get(Page, page.id).token_count == 0
        assert session.get(Page, page.id).indexed_at is not None


@pytest.mark.integration
def test_index_page_skips_duplicate_content_hash_in_same_job(test_database_url: str) -> None:
    mk = _mk_session(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://idx-dup.example/",
            normalized_seed_url="https://idx-dup.example/",
            status="queued",
        )
        session.add(job)
        session.commit()

        body = "Same extracted text across multiple URLs"

        p1 = Page(
            crawl_job_id=job.id,
            url="https://idx-dup.example/a",
            normalized_url="https://idx-dup.example/a",
            domain="idx-dup.example",
            title="Alpha",
            extracted_text=body,
            content_hash="samehash",
            status_code=200,
            depth=0,
        )
        p2 = Page(
            crawl_job_id=job.id,
            url="https://idx-dup.example/b",
            normalized_url="https://idx-dup.example/b",
            domain="idx-dup.example",
            title="Beta",
            extracted_text=body,
            content_hash="samehash",
            status_code=200,
            depth=0,
        )
        session.add(p1)
        session.add(p2)
        session.commit()

        index_page(session, p1.id)
        session.commit()

        postings_first = session.scalars(select(InvertedIndex).where(InvertedIndex.page_id == p1.id)).all()
        assert len(postings_first) > 0

        index_page(session, p2.id)
        session.commit()

        postings_second = session.scalars(select(InvertedIndex).where(InvertedIndex.page_id == p2.id)).all()
        assert postings_second == []
        assert session.get(Page, p2.id).token_count == 0

