"""Search indexed pages using the inverted index."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from crawliq_core.tokenize import tokenize
from models.domain import InvertedIndex, Page, Term


@dataclass(frozen=True)
class _RankedPage:
    page_id: int
    score: float
    matched_terms: frozenset[str]


def _collection_page_count(session: Session, *, crawl_job_id: int | None) -> int:
    """Number of pages considered indexed for this search scope."""
    stmt = select(func.count()).select_from(Page).where(Page.indexed_at.isnot(None))
    if crawl_job_id is not None:
        stmt = stmt.where(Page.crawl_job_id == crawl_job_id)
    count = session.scalar(stmt)
    return int(count or 0)


def _smooth_inverse_document_frequency(
    indexed_page_count: int,
    document_frequency: int,
) -> float:
    """
    Smooth IDF so rare terms get a modest boost and df=0 does not explode.

    Uses a common smoothed form: log(N / (df + 1)) + 1, where N is the
    number of indexed pages in scope.
    """
    n = max(indexed_page_count, 1)
    df = max(int(document_frequency), 0)
    return math.log(n / (df + 1.0) + 1.0)


def _build_snippet(
    *,
    title: str | None,
    body: str | None,
    highlight_terms: frozenset[str],
    max_visible_chars: int = 180,
) -> str:
    """
    Short excerpt from title/body with an attempt to show a matched term.
    """
    if not highlight_terms:
        source = (body or title or "").strip()
        return source[:max_visible_chars] if source else ""

    haystack = (body or "").strip()
    if not haystack:
        haystack = (title or "").strip()
    if not haystack:
        return ""

    lowered = haystack.casefold()
    best_start = 0
    for term in highlight_terms:
        pos = lowered.find(term)
        if pos >= 0:
            best_start = max(0, pos - 40)
            break

    chunk = haystack[best_start : best_start + max_visible_chars].strip()
    if len(haystack) > len(chunk):
        chunk = f"{chunk}…"
    return chunk


def _strip_repeated_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def execute_search(
    session: Session,
    *,
    raw_query: str,
    crawl_job_id: int | None,
    result_limit: int,
) -> tuple[list[_RankedPage], int]:
    """
    Return ranked page hits and the number of indexed pages considered in scope.

    Scoring: sum over query tokens of (query_token_weight * tf * idf(term)).
    """
    query_term_weights: Counter[str] = Counter(tokenize(raw_query))
    if not query_term_weights:
        return [], _collection_page_count(session, crawl_job_id=crawl_job_id)

    indexed_page_count = _collection_page_count(session, crawl_job_id=crawl_job_id)

    term_rows = session.scalars(
        select(Term).where(Term.term.in_(list(query_term_weights.keys()))),
    ).all()
    term_by_key: dict[str, Term] = {row.term: row for row in term_rows}

    page_score_by_id: dict[int, float] = defaultdict(float)
    matched_terms_by_page: dict[int, set[str]] = defaultdict(set)

    for query_term, query_weight in query_term_weights.items():
        term_row = term_by_key.get(query_term)
        if term_row is None:
            continue

        idf_weight = _smooth_inverse_document_frequency(
            indexed_page_count,
            int(term_row.document_frequency or 0),
        )

        filters = [
            InvertedIndex.term_id == term_row.id,
            Page.indexed_at.isnot(None),
        ]
        if crawl_job_id is not None:
            filters.append(Page.crawl_job_id == crawl_job_id)

        stmt = (
            select(InvertedIndex.page_id, InvertedIndex.term_frequency)
            .join(Page, Page.id == InvertedIndex.page_id)
            .where(and_(*filters))
        )

        for page_id, term_frequency in session.execute(stmt):
            contribution = float(term_frequency) * idf_weight * float(query_weight)
            page_score_by_id[int(page_id)] += contribution
            matched_terms_by_page[int(page_id)].add(query_term)

    ranked = sorted(
        (
            _RankedPage(
                page_id=pid,
                score=score,
                matched_terms=frozenset(matched_terms_by_page.get(pid, set())),
            )
            for pid, score in page_score_by_id.items()
        ),
        key=lambda row: row.score,
        reverse=True,
    )[:result_limit]

    return ranked, indexed_page_count


def search_indexed_pages(
    session: Session,
    *,
    raw_query: str,
    crawl_job_id: int | None,
    result_limit: int,
) -> list[dict]:
    """
    Run search and return rows suitable for ``SearchResponse``.

    Each dict has keys: page_id, title, url, score, snippet, matched_terms (sorted list).
    """
    ranked_pages, _ = execute_search(
        session,
        raw_query=raw_query,
        crawl_job_id=crawl_job_id,
        result_limit=result_limit,
    )
    if not ranked_pages:
        return []

    page_ids = [row.page_id for row in ranked_pages]
    pages = session.scalars(select(Page).where(Page.id.in_(page_ids))).all()
    page_by_id = {p.id: p for p in pages}

    ordered_rows: list[dict] = []
    for ranked in ranked_pages:
        page = page_by_id.get(ranked.page_id)
        if page is None:
            continue
        matched = sorted(ranked.matched_terms)
        snippet = _strip_repeated_ws(
            _build_snippet(
                title=page.title,
                body=page.extracted_text,
                highlight_terms=ranked.matched_terms,
            ),
        )
        ordered_rows.append(
            {
                "page_id": int(page.id),
                "title": page.title,
                "url": page.url,
                "score": round(float(ranked.score), 4),
                "snippet": snippet,
                "matched_terms": matched,
            },
        )

    return ordered_rows
