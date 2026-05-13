"""Populate ``page_graph_edges`` with ``edge_type = content_similarity`` from TF–IDF + cosine."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from config import Settings, get_settings
from models.domain import InvertedIndex, Page, PageGraphEdge, Term

SIMILARITY_EVIDENCE_SOURCE = "inverted_index_tfidf_cosine"
_IMPORTANT_TERMS_PER_PAGE = 20
_MAX_SHARED_TERMS_IN_EVIDENCE = 40
_INSERT_BATCH = 500
_SIMILARITY_ROUND_DECIMALS = 6


def _job_local_idf(*, n_docs: int, df: int) -> float:
    """Smoothed IDF over documents in this crawl job only."""
    return math.log((n_docs + 1) / (df + 1))


def _cosine_sparse(
    wp: dict[int, float],
    wq: dict[int, float],
    norm_p: float,
    norm_q: float,
) -> float:
    if norm_p <= 0.0 or norm_q <= 0.0:
        return 0.0
    if len(wp) <= len(wq):
        dot = sum(wq[t] * v for t, v in wp.items() if t in wq)
    else:
        dot = sum(wp[t] * v for t, v in wq.items() if t in wp)
    return dot / (norm_p * norm_q)


def _important_term_ids(weights: dict[int, float], *, limit: int) -> list[int]:
    if not weights:
        return []
    ranked = sorted(weights.items(), key=lambda tv: (-tv[1], tv[0]))
    return [t for t, _ in ranked[:limit]]


@dataclass(frozen=True)
class JobTfidfContext:
    """Job-local inverted-index vectors for cosine similarity (pages with postings only)."""

    page_vec: dict[int, dict[int, float]]
    page_norm: dict[int, float]
    term_to_pages: dict[int, set[int]]
    term_label: dict[int, str]


def load_job_tfidf_context(session: Session, crawl_job_id: int) -> JobTfidfContext | None:
    """
    Build TF–IDF sparse vectors per page from ``inverted_index`` for one crawl job.
    Returns ``None`` if fewer than two pages have postings.
    """
    rows = session.execute(
        select(
            InvertedIndex.page_id,
            InvertedIndex.term_id,
            InvertedIndex.term_frequency,
            Term.term,
        )
        .join(Page, Page.id == InvertedIndex.page_id)
        .join(Term, Term.id == InvertedIndex.term_id)
        .where(Page.crawl_job_id == crawl_job_id),
    ).all()

    if not rows:
        return None

    page_tf: dict[int, dict[int, int]] = defaultdict(dict)
    term_to_pages: dict[int, set[int]] = defaultdict(set)
    term_label: dict[int, str] = {}

    for page_id, term_id, tf, term in rows:
        page_tf[page_id][term_id] = int(tf)
        term_to_pages[term_id].add(page_id)
        term_label[term_id] = term

    page_ids = list(page_tf.keys())
    n_docs = len(page_ids)
    if n_docs < 2:
        return None

    df_by_term = {t: len(pages) for t, pages in term_to_pages.items()}
    idf_by_term = {t: _job_local_idf(n_docs=n_docs, df=df) for t, df in df_by_term.items()}

    page_vec: dict[int, dict[int, float]] = {}
    page_norm: dict[int, float] = {}
    for pid in page_ids:
        w: dict[int, float] = {}
        sq = 0.0
        for tid, tf in page_tf[pid].items():
            wt = float(tf) * idf_by_term[tid]
            w[tid] = wt
            sq += wt * wt
        page_vec[pid] = w
        page_norm[pid] = math.sqrt(sq) if sq > 0.0 else 0.0

    return JobTfidfContext(
        page_vec=page_vec,
        page_norm=page_norm,
        term_to_pages=term_to_pages,
        term_label=term_label,
    )


def _evidence_dict(
    *,
    shared_term_ids: list[int],
    term_label: dict[int, str],
    similarity: float,
) -> dict[str, Any]:
    labels = sorted({term_label[t] for t in shared_term_ids if t in term_label})[:_MAX_SHARED_TERMS_IN_EVIDENCE]
    return {
        "shared_terms": labels,
        "similarity": round(float(similarity), _SIMILARITY_ROUND_DECIMALS),
        "source": SIMILARITY_EVIDENCE_SOURCE,
    }


def generate_content_similarity_edges_for_job(
    session: Session,
    crawl_job_id: int,
    *,
    settings: Settings | None = None,
    top_k: int | None = None,
    min_score: float | None = None,
) -> int:
    """
    Directed ``content_similarity`` edges: for each page with postings, up to ``top_k``
    outgoing neighbors by cosine TF–IDF similarity (job-local IDF), score ≥ ``min_score``,
    candidates must share at least one of that page's top-weight terms. Idempotent via
    ``ON CONFLICT DO NOTHING``.
    """
    cfg = settings or get_settings()
    k = int(top_k if top_k is not None else cfg.graph_similarity_top_k)
    min_s = float(min_score if min_score is not None else cfg.graph_similarity_min_score)

    ctx = load_job_tfidf_context(session, crawl_job_id)
    if ctx is None:
        return 0

    page_vec = ctx.page_vec
    page_norm = ctx.page_norm
    term_to_pages = ctx.term_to_pages
    term_label = ctx.term_label
    page_ids = list(page_vec.keys())

    batch: list[dict[str, Any]] = []
    inserted_total = 0

    def flush() -> None:
        nonlocal batch, inserted_total
        if not batch:
            return
        stmt = (
            pg_insert(PageGraphEdge.__table__)
            .values(batch)
            .on_conflict_do_nothing(constraint="uq_page_graph_edges_job_src_tgt_type")
        )
        res = session.execute(stmt)
        inserted_total += int(res.rowcount or 0)
        batch.clear()

    for src in sorted(page_ids):
        w_src = page_vec[src]
        n_src = page_norm[src]
        if n_src <= 0.0:
            continue

        important = _important_term_ids(w_src, limit=_IMPORTANT_TERMS_PER_PAGE)
        if not important:
            continue

        candidates: set[int] = set()
        for tid in important:
            candidates.update(term_to_pages.get(tid, ()))
        candidates.discard(src)
        if not candidates:
            continue

        scored: list[tuple[float, int]] = []
        for tgt in candidates:
            if tgt == src:
                continue
            w_tgt = page_vec[tgt]
            n_tgt = page_norm[tgt]
            sim = _cosine_sparse(w_src, w_tgt, n_src, n_tgt)
            if sim < min_s:
                continue
            scored.append((sim, tgt))

        scored.sort(key=lambda st: (-st[0], st[1]))
        for sim, tgt in scored[:k]:
            shared_ids = sorted(set(w_src) & set(w_tgt))
            ev = _evidence_dict(
                shared_term_ids=shared_ids,
                term_label=term_label,
                similarity=sim,
            )
            batch.append(
                {
                    "crawl_job_id": crawl_job_id,
                    "source_page_id": src,
                    "target_page_id": tgt,
                    "edge_type": "content_similarity",
                    "weight": float(sim),
                    "evidence": ev,
                },
            )
            if len(batch) >= _INSERT_BATCH:
                flush()

    flush()
    return inserted_total
