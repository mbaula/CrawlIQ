"""Index one page into the inverted index (terms + postings)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import delete, select
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
        existing = session.scalars(select(Term).where(Term.term.in_(list(tf.keys())))).all()
        by_term = {t.term: t for t in existing}

        term_ids: dict[str, int] = {}
        for term in tf.keys():
            row = by_term.get(term)
            if row is None:
                row = Term(term=term, document_frequency=0)
                session.add(row)
                session.flush()  # allocate id
                by_term[term] = row
            term_ids[term] = row.id

        for term in tf.keys():
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

