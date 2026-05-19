"""Search indexed pages using BM25 ranking."""

from __future__ import annotations

import heapq
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


def _compute_scoped_document_frequencies_batch(
    session: Session,
    term_ids: list[int],
    crawl_job_id: int,
) -> dict[int, int]:
    """Per-term document frequency within a crawl job (indexed pages with token_count > 0)."""
    if not term_ids:
        return {}
    stmt = (
        select(InvertedIndex.term_id, func.count(InvertedIndex.page_id.distinct()))
        .join(Page, Page.id == InvertedIndex.page_id)
        .where(
            and_(
                InvertedIndex.term_id.in_(term_ids),
                Page.crawl_job_id == crawl_job_id,
                Page.indexed_at.isnot(None),
                Page.token_count > 0,
            ),
        )
        .group_by(InvertedIndex.term_id)
    )
    return {int(tid): int(cnt or 0) for tid, cnt in session.execute(stmt)}


def _build_snippet(
    *,
    title: str | None,
    body: str | None,
    highlight_terms: frozenset[str],
    max_visible_chars: int = 200,
) -> str:
    """
    Short excerpt from body (or title) that maximizes matched term coverage.

    Scans for all term positions and picks the window containing the most
    distinct matched terms.
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
    term_positions: list[tuple[int, str]] = []
    for term in highlight_terms:
        start = 0
        while True:
            pos = lowered.find(term, start)
            if pos < 0:
                break
            term_positions.append((pos, term))
            start = pos + 1

    if not term_positions:
        chunk = haystack[:max_visible_chars].strip()
        if len(haystack) > len(chunk):
            chunk = f"{chunk}…"
        return chunk

    term_positions.sort(key=lambda x: x[0])

    best_start = 0
    best_term_count = 0

    for anchor_pos, _ in term_positions:
        window_start = max(0, anchor_pos - 40)
        window_end = window_start + max_visible_chars
        terms_in_window = {
            t for (p, t) in term_positions if window_start <= p < window_end
        }
        if len(terms_in_window) > best_term_count:
            best_term_count = len(terms_in_window)
            best_start = window_start

    chunk = haystack[best_start : best_start + max_visible_chars].strip()
    prefix = "…" if best_start > 0 else ""
    suffix = "…" if best_start + max_visible_chars < len(haystack) else ""
    return f"{prefix}{chunk}{suffix}"


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
    ranked_full, corpus_stats = execute_search_ranked_pages(
        session,
        raw_query=raw_query,
        crawl_job_id=crawl_job_id,
        max_ranked=result_limit,
    )
    return ranked_full, corpus_stats


def execute_search_ranked_pages(
    session: Session,
    *,
    raw_query: str,
    crawl_job_id: int | None,
    max_ranked: int | None = None,
) -> tuple[list[_RankedPage], _CorpusStats]:
    """
    Same BM25 scoring as ``execute_search``, but returns the full sorted list (optionally capped).

    When ``max_ranked`` is set, only the first ``max_ranked`` rows are kept (still sorted by score).
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

    term_ids_for_df = [t.id for t in term_rows]
    scoped_df_by_term_id: dict[int, int] = {}
    if crawl_job_id is not None and term_ids_for_df:
        scoped_df_by_term_id = _compute_scoped_document_frequencies_batch(
            session,
            term_ids_for_df,
            crawl_job_id,
        )

    page_score_by_id: dict[int, float] = defaultdict(float)
    matched_terms_by_page: dict[int, set[str]] = defaultdict(set)

    for query_term, query_weight in query_term_weights.items():
        term_row = term_by_key.get(query_term)
        if term_row is None:
            continue

        if crawl_job_id is not None:
            document_frequency = scoped_df_by_term_id.get(term_row.id, 0)
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

            bm25_contribution = _bm25_term_score(
                term_frequency=int(term_frequency),
                document_length=int(token_count),
                average_document_length=corpus_stats.average_token_count,
                idf=idf,
            )
            page_score_by_id[page_id] += bm25_contribution * float(query_weight)
            matched_terms_by_page[page_id].add(query_term)

    total_candidates = len(page_score_by_id)
    if total_candidates == 0:
        return [], corpus_stats

    n_keep = total_candidates
    if max_ranked is not None:
        n_keep = min(max(0, max_ranked), total_candidates)

    ranked_iter = (
        _RankedPage(
            page_id=pid,
            score=score,
            matched_terms=frozenset(matched_terms_by_page.get(pid, set())),
        )
        for pid, score in page_score_by_id.items()
    )
    ranked_full = heapq.nlargest(
        n_keep,
        ranked_iter,
        key=lambda row: (row.score, -row.page_id),
    )

    return ranked_full, corpus_stats


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

    When searching across all jobs (crawl_job_id is None), results are deduplicated
    by URL, keeping the highest-scoring result for each unique URL.
    """
    fetch_limit = result_limit if crawl_job_id is not None else result_limit * 5

    ranked_pages, _ = execute_search(
        session,
        raw_query=raw_query,
        crawl_job_id=crawl_job_id,
        result_limit=fetch_limit,
    )
    if not ranked_pages:
        return []

    page_ids = [row.page_id for row in ranked_pages]
    pages = session.scalars(select(Page).where(Page.id.in_(page_ids))).all()
    page_by_id = {p.id: p for p in pages}

    ordered_rows: list[dict] = []
    seen_urls: set[str] = set()

    for ranked in ranked_pages:
        page = page_by_id.get(ranked.page_id)
        if page is None:
            continue

        if crawl_job_id is None and page.url in seen_urls:
            continue
        seen_urls.add(page.url)

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
                "score_components": None,
                "score_explanation": None,
            },
        )

        if len(ordered_rows) >= result_limit:
            break

    return ordered_rows
