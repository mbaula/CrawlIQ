"""Search indexed pages using BM25 ranking."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from crawliq_core.tokenize import tokenize
from models.domain import InvertedIndex, Page, Term

BM25_K1 = 1.5
BM25_B = 0.75


@dataclass(frozen=True)
class _RankedPage:
    page_id: int
    score: float
    matched_terms: frozenset[str]


@dataclass(frozen=True)
class _CorpusStats:
    indexed_page_count: int
    average_token_count: float


def _compute_corpus_stats(session: Session, *, crawl_job_id: int | None) -> _CorpusStats:
    """
    Compute N and avgdl for BM25.

    Only considers pages where indexed_at is set AND token_count > 0.
    """
    base_filters = [
        Page.indexed_at.isnot(None),
        Page.token_count > 0,
    ]
    if crawl_job_id is not None:
        base_filters.append(Page.crawl_job_id == crawl_job_id)

    stmt = select(
        func.count(),
        func.coalesce(func.avg(Page.token_count), 0),
    ).where(and_(*base_filters))

    row = session.execute(stmt).one()
    count = int(row[0] or 0)
    avg_tokens = float(row[1] or 0)
    return _CorpusStats(indexed_page_count=count, average_token_count=avg_tokens)


def _bm25_idf(total_docs: int, document_frequency: int) -> float:
    """
    BM25 IDF: ln(1 + (N - df + 0.5) / (df + 0.5))

    Returns 0 if total_docs is 0 to avoid invalid scores.
    """
    n = max(total_docs, 0)
    df = max(document_frequency, 0)
    if n == 0:
        return 0.0
    numerator = n - df + 0.5
    denominator = df + 0.5
    return math.log(1.0 + numerator / denominator)


def _bm25_term_score(
    term_frequency: int,
    document_length: int,
    average_document_length: float,
    idf: float,
) -> float:
    """
    BM25 term contribution:

        IDF * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (dl / avgdl)))
    """
    tf = float(term_frequency)
    dl = float(document_length)
    avgdl = average_document_length if average_document_length > 0 else 1.0

    length_norm = 1.0 - BM25_B + BM25_B * (dl / avgdl)
    numerator = tf * (BM25_K1 + 1.0)
    denominator = tf + BM25_K1 * length_norm

    return idf * (numerator / denominator)


def _compute_scoped_document_frequency(
    session: Session,
    term_id: int,
    crawl_job_id: int,
) -> int:
    """
    Count how many indexed pages (token_count > 0) in the given job contain this term.
    """
    stmt = (
        select(func.count(InvertedIndex.page_id.distinct()))
        .join(Page, Page.id == InvertedIndex.page_id)
        .where(
            and_(
                InvertedIndex.term_id == term_id,
                Page.crawl_job_id == crawl_job_id,
                Page.indexed_at.isnot(None),
                Page.token_count > 0,
            ),
        )
    )
    result = session.scalar(stmt)
    return int(result or 0)


def _build_snippet(
    *,
    title: str | None,
    body: str | None,
    highlight_terms: frozenset[str],
    max_visible_chars: int = 180,
) -> str:
    """Short excerpt from title/body biased toward a matched term."""
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
) -> tuple[list[_RankedPage], _CorpusStats]:
    """
    Return ranked page hits (BM25) and corpus stats.

    Scoring uses BM25 with k1=1.5, b=0.75. Query term counts act as multipliers.
    """
    query_term_weights: Counter[str] = Counter(tokenize(raw_query))
    corpus_stats = _compute_corpus_stats(session, crawl_job_id=crawl_job_id)

    if not query_term_weights:
        return [], corpus_stats

    if corpus_stats.indexed_page_count == 0 or corpus_stats.average_token_count <= 0:
        return [], corpus_stats

    term_rows = session.scalars(
        select(Term).where(Term.term.in_(list(query_term_weights.keys()))),
    ).all()
    term_by_key: dict[str, Term] = {row.term: row for row in term_rows}

    page_score_by_id: dict[int, float] = defaultdict(float)
    matched_terms_by_page: dict[int, set[str]] = defaultdict(set)
    page_token_count_cache: dict[int, int] = {}

    for query_term, query_weight in query_term_weights.items():
        term_row = term_by_key.get(query_term)
        if term_row is None:
            continue

        if crawl_job_id is not None:
            document_frequency = _compute_scoped_document_frequency(
                session,
                term_row.id,
                crawl_job_id,
            )
        else:
            document_frequency = int(term_row.document_frequency or 0)

        idf = _bm25_idf(corpus_stats.indexed_page_count, document_frequency)
        if idf <= 0:
            continue

        page_filters = [
            InvertedIndex.term_id == term_row.id,
            Page.indexed_at.isnot(None),
            Page.token_count > 0,
        ]
        if crawl_job_id is not None:
            page_filters.append(Page.crawl_job_id == crawl_job_id)

        stmt = (
            select(InvertedIndex.page_id, InvertedIndex.term_frequency, Page.token_count)
            .join(Page, Page.id == InvertedIndex.page_id)
            .where(and_(*page_filters))
        )

        for page_id, term_frequency, token_count in session.execute(stmt):
            page_id = int(page_id)
            page_token_count_cache[page_id] = int(token_count)

            bm25_contribution = _bm25_term_score(
                term_frequency=int(term_frequency),
                document_length=int(token_count),
                average_document_length=corpus_stats.average_token_count,
                idf=idf,
            )
            page_score_by_id[page_id] += bm25_contribution * float(query_weight)
            matched_terms_by_page[page_id].add(query_term)

    ranked = sorted(
        (
            _RankedPage(
                page_id=pid,
                score=score,
                matched_terms=frozenset(matched_terms_by_page.get(pid, set())),
            )
            for pid, score in page_score_by_id.items()
        ),
        key=lambda row: (-row.score, row.page_id),
    )[:result_limit]

    return ranked, corpus_stats


def search_indexed_pages(
    session: Session,
    *,
    raw_query: str,
    crawl_job_id: int | None,
    result_limit: int,
) -> list[dict]:
    """
    Run BM25 search and return rows suitable for ``SearchResponse``.

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
