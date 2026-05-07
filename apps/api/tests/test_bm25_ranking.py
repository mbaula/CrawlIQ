"""BM25 ranking tests with synthetic pages."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.url import sync_engine_url
from models.domain import CrawlJob, Page
from services.index_page import index_page
from services.search_pages import execute_search


def _mk_session(test_database_url: str):
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _create_page(
    session,
    job_id: int,
    url_suffix: str,
    title: str,
    body: str,
) -> Page:
    page = Page(
        crawl_job_id=job_id,
        url=f"https://bm25.example/{url_suffix}",
        normalized_url=f"https://bm25.example/{url_suffix}",
        domain="bm25.example",
        title=title,
        extracted_text=body,
        status_code=200,
        depth=0,
        fetched_at=datetime.now(timezone.utc),
    )
    session.add(page)
    session.commit()
    index_page(session, page.id)
    session.commit()
    return page


@pytest.mark.integration
def test_rare_term_beats_common_term(test_database_url: str) -> None:
    """A page matching a rare term should rank higher than one matching a common term."""
    mk = _mk_session(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://bm25.example/rare",
            normalized_seed_url="https://bm25.example/rare",
            status="completed",
        )
        session.add(job)
        session.commit()

        common_word = "framework"
        rare_word = "xylophonequux"

        for i in range(5):
            _create_page(
                session,
                job.id,
                f"common{i}",
                title=f"Page {i}",
                body=f"This is about the {common_word} and other topics.",
            )

        rare_page = _create_page(
            session,
            job.id,
            "rare",
            title="Rare Page",
            body=f"This mentions {rare_word} which is unique.",
        )

        common_page = _create_page(
            session,
            job.id,
            "common_target",
            title="Common Target",
            body=f"This also talks about the {common_word}.",
        )

        ranked_rare, _ = execute_search(
            session,
            raw_query=rare_word,
            crawl_job_id=job.id,
            result_limit=10,
        )
        ranked_common, _ = execute_search(
            session,
            raw_query=common_word,
            crawl_job_id=job.id,
            result_limit=10,
        )

        assert len(ranked_rare) == 1
        assert ranked_rare[0].page_id == rare_page.id

        assert len(ranked_common) >= 2
        rare_score = ranked_rare[0].score if ranked_rare else 0
        common_scores = [r.score for r in ranked_common]

        assert rare_score > max(common_scores), "Rare term should yield higher score than common term"


@pytest.mark.integration
def test_repeated_term_helps_but_saturates(test_database_url: str) -> None:
    """A page with 10x term occurrences should not have 10x score."""
    mk = _mk_session(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://bm25.example/saturation",
            normalized_seed_url="https://bm25.example/saturation",
            status="completed",
        )
        session.add(job)
        session.commit()

        keyword = "uniquesaturationword"

        page_1x = _create_page(
            session,
            job.id,
            "1x",
            title="Single",
            body=f"Contains {keyword} once with some padding text here.",
        )

        page_10x = _create_page(
            session,
            job.id,
            "10x",
            title="Many",
            body=f"{keyword} " * 10 + "some padding text.",
        )

        ranked, _ = execute_search(
            session,
            raw_query=keyword,
            crawl_job_id=job.id,
            result_limit=10,
        )

        assert len(ranked) == 2
        scores = {r.page_id: r.score for r in ranked}

        score_1x = scores[page_1x.id]
        score_10x = scores[page_10x.id]

        assert score_10x > score_1x, "More occurrences should help"
        assert score_10x < score_1x * 10, "BM25 should saturate TF"


@pytest.mark.integration
def test_short_relevant_doc_beats_long_noisy_doc(test_database_url: str) -> None:
    """A short focused doc should beat a long doc that barely mentions the term."""
    mk = _mk_session(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://bm25.example/length",
            normalized_seed_url="https://bm25.example/length",
            status="completed",
        )
        session.add(job)
        session.commit()

        keyword = "targetkeywordxyz"
        filler = "lorem ipsum dolor sit amet consectetur adipiscing elit " * 50

        short_page = _create_page(
            session,
            job.id,
            "short",
            title=keyword,
            body=f"This is about {keyword}. Concise and relevant.",
        )

        long_page = _create_page(
            session,
            job.id,
            "long",
            title="Generic Long Page",
            body=f"{filler} oh and also {keyword} somewhere {filler}",
        )

        ranked, _ = execute_search(
            session,
            raw_query=keyword,
            crawl_job_id=job.id,
            result_limit=10,
        )

        assert len(ranked) == 2
        assert ranked[0].page_id == short_page.id, "Short focused doc should rank first"


@pytest.mark.integration
def test_job_scoped_search_uses_scoped_stats(test_database_url: str) -> None:
    """Searching within a job should use that job's corpus stats, not global."""
    mk = _mk_session(test_database_url)
    with mk() as session:
        job_a = CrawlJob(
            seed_url="https://bm25.example/scope-a",
            normalized_seed_url="https://bm25.example/scope-a",
            status="completed",
        )
        job_b = CrawlJob(
            seed_url="https://bm25.example/scope-b",
            normalized_seed_url="https://bm25.example/scope-b",
            status="completed",
        )
        session.add(job_a)
        session.add(job_b)
        session.commit()

        keyword = "scopedtermxyz"

        for i in range(10):
            _create_page(
                session,
                job_a.id,
                f"a{i}",
                title=f"Job A Page {i}",
                body=f"Contains {keyword} in every page.",
            )

        page_b = _create_page(
            session,
            job_b.id,
            "b0",
            title="Job B Only Page",
            body=f"This is the only page with {keyword} in job B.",
        )

        ranked_in_a, stats_a = execute_search(
            session,
            raw_query=keyword,
            crawl_job_id=job_a.id,
            result_limit=20,
        )
        ranked_in_b, stats_b = execute_search(
            session,
            raw_query=keyword,
            crawl_job_id=job_b.id,
            result_limit=20,
        )

        assert stats_a.indexed_page_count == 10
        assert stats_b.indexed_page_count == 1
        assert len(ranked_in_a) == 10
        assert len(ranked_in_b) == 1
        assert ranked_in_b[0].page_id == page_b.id


@pytest.mark.integration
def test_zero_token_count_pages_excluded(test_database_url: str) -> None:
    """Pages with token_count=0 should not affect stats or appear in results."""
    mk = _mk_session(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://bm25.example/zero",
            normalized_seed_url="https://bm25.example/zero",
            status="completed",
        )
        session.add(job)
        session.commit()

        keyword = "zerotestword"

        good_page = _create_page(
            session,
            job.id,
            "good",
            title=keyword,
            body=f"This page has content about {keyword}.",
        )

        empty_page = Page(
            crawl_job_id=job.id,
            url="https://bm25.example/empty",
            normalized_url="https://bm25.example/empty",
            domain="bm25.example",
            title="",
            extracted_text="the and of to",
            status_code=200,
            depth=0,
            fetched_at=datetime.now(timezone.utc),
        )
        session.add(empty_page)
        session.commit()
        index_page(session, empty_page.id)
        session.commit()

        session.refresh(empty_page)
        assert empty_page.token_count == 0

        ranked, stats = execute_search(
            session,
            raw_query=keyword,
            crawl_job_id=job.id,
            result_limit=10,
        )

        assert stats.indexed_page_count == 1
        assert len(ranked) == 1
        assert ranked[0].page_id == good_page.id


@pytest.mark.integration
def test_deterministic_tie_breaking(test_database_url: str) -> None:
    """Pages with equal scores should be ordered by page_id for stability."""
    mk = _mk_session(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://bm25.example/tie",
            normalized_seed_url="https://bm25.example/tie",
            status="completed",
        )
        session.add(job)
        session.commit()

        keyword = "identicalterm"
        body_text = f"This page mentions {keyword} exactly once with identical length."

        pages = []
        for i in range(5):
            p = _create_page(
                session,
                job.id,
                f"tie{i}",
                title="Same Title",
                body=body_text,
            )
            pages.append(p)

        ranked1, _ = execute_search(
            session,
            raw_query=keyword,
            crawl_job_id=job.id,
            result_limit=10,
        )
        ranked2, _ = execute_search(
            session,
            raw_query=keyword,
            crawl_job_id=job.id,
            result_limit=10,
        )

        ids1 = [r.page_id for r in ranked1]
        ids2 = [r.page_id for r in ranked2]
        assert ids1 == ids2, "Results should be deterministic"

        for i in range(len(ids1) - 1):
            if ranked1[i].score == ranked1[i + 1].score:
                assert ids1[i] < ids1[i + 1], "Ties should be broken by page_id ASC"


@pytest.mark.integration
def test_title_match_beats_body_only_match(test_database_url: str) -> None:
    """A page with the term in title should rank higher than body-only."""
    mk = _mk_session(test_database_url)
    with mk() as session:
        job = CrawlJob(
            seed_url="https://bm25.example/title",
            normalized_seed_url="https://bm25.example/title",
            status="completed",
        )
        session.add(job)
        session.commit()

        keyword = "titletestword"

        title_page = _create_page(
            session,
            job.id,
            "title_match",
            title=keyword,
            body="Some generic content without the keyword.",
        )

        body_page = _create_page(
            session,
            job.id,
            "body_match",
            title="Generic Title",
            body=f"This body contains {keyword} but title does not.",
        )

        ranked, _ = execute_search(
            session,
            raw_query=keyword,
            crawl_job_id=job.id,
            result_limit=10,
        )

        assert len(ranked) == 2
        assert ranked[0].page_id == title_page.id, "Title match should rank first"
