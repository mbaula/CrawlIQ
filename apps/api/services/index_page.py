"""Index one page into the inverted index (terms + postings)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import time

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from crawliq_core.tokenize import tokenize
from models.domain import CrawlJob, InvertedIndex, Page, Term


def _tf_map(*, title: str | None, body: str | None, title_weight: int) -> tuple[dict[str, int], int]:
    title_tokens = tokenize(title or "")
    body_tokens = tokenize(body or "")

    token_count = len(body_tokens) + (len(title_tokens) * title_weight)

    counts: Counter[str] = Counter(body_tokens)
    if title_weight > 0 and title_tokens:
        for t in title_tokens:
            counts[t] += title_weight
    return dict(counts), token_count


def _get_or_create_term_ids(session: Session, terms: list[str]) -> dict[str, int]:
    """
    Concurrency-safe term id allocation.

    Uses INSERT..ON CONFLICT DO NOTHING to avoid deadlocks when multiple workers
    race to create the same term rows.
    """
    if not terms:
        return {}

    unique_terms = sorted(set(terms))

    # Insert any missing terms without raising on unique constraint races.
    stmt = (
        pg_insert(Term)
        .values([{"term": t, "document_frequency": 0} for t in unique_terms])
        .on_conflict_do_nothing(index_elements=[Term.__table__.c.term])
        .returning(Term.__table__.c.term, Term.__table__.c.id)
    )
    inserted = dict(session.execute(stmt).all())

    missing = [t for t in unique_terms if t not in inserted]
    if not missing:
        return inserted

    existing = dict(session.execute(select(Term.term, Term.id).where(Term.term.in_(missing))).all())
    return {**existing, **inserted}


def _with_deadlock_retry(fn, *, max_attempts: int = 5):
    # We retry a few times on Postgres deadlocks (40P01). This is expected under
    # high concurrency, and safe here because the whole operation is idempotent
    # within the surrounding transaction.
    for attempt in range(max_attempts):
        try:
            return fn()
        except OperationalError as e:
            pgcode = getattr(getattr(e, "orig", None), "pgcode", None)
            if pgcode != "40P01" or attempt >= (max_attempts - 1):
                raise
            time.sleep(0.05 * (2**attempt))


def index_page(session: Session, page_id: int, *, title_weight: int = 3) -> None:
    """
    (Re)index ``page_id``.

    Idempotent: safe to call multiple times. Uses delete-and-rebuild for postings.
    Updates ``terms.document_frequency`` based on whether the page contains the term.
    Sets ``pages.indexed_at`` and ``pages.token_count``. Increments
    ``crawl_jobs.pages_indexed`` only the first time the page is indexed.
    """
    page = session.get(Page, page_id)
    if page is None:
        return

    job = session.get(CrawlJob, page.crawl_job_id)
    if job is None:
        return

    was_indexed = page.indexed_at is not None

    # Duplicate content detection: if another already-indexed page in the same crawl job
    # has the same extracted-text hash, skip postings for this page so duplicates don't
    # pollute the search index.
    if page.content_hash:
        existing_indexed_page_id = session.scalar(
            select(Page.id).where(
                Page.crawl_job_id == page.crawl_job_id,
                Page.content_hash == page.content_hash,
                Page.id != page_id,
                Page.indexed_at.isnot(None),
                Page.token_count > 0,
            ),
        )
        if existing_indexed_page_id is not None:
            page.indexed_at = datetime.now(timezone.utc)
            page.token_count = 0
            return

    old_term_ids = set(
        session.scalars(
            select(InvertedIndex.term_id).where(InvertedIndex.page_id == page_id),
        ).all(),
    )

    if old_term_ids:
        session.execute(delete(InvertedIndex).where(InvertedIndex.page_id == page_id))
        terms = session.scalars(select(Term).where(Term.id.in_(old_term_ids))).all()
        for t in terms:
            if (t.document_frequency or 0) > 0:
                t.document_frequency = t.document_frequency - 1

    tf, token_count = _tf_map(
        title=page.title,
        body=page.extracted_text,
        title_weight=title_weight,
    )

    if tf:
        terms = list(tf.keys())

        term_ids = _with_deadlock_retry(lambda: _get_or_create_term_ids(session, terms))
        by_term = {
            t.term: t
            for t in session.scalars(select(Term).where(Term.term.in_(terms))).all()
        }

        for term in terms:
            by_term[term].document_frequency = (by_term[term].document_frequency or 0) + 1

        session.add_all(
            [
                InvertedIndex(term_id=term_ids[term], page_id=page_id, term_frequency=freq)
                for term, freq in tf.items()
                if freq > 0
            ],
        )

    page.indexed_at = datetime.now(timezone.utc)
    page.token_count = int(token_count)
    if not was_indexed:
        job.pages_indexed = job.pages_indexed + 1

