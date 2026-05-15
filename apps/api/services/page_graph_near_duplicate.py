"""Populate ``page_graph_edges`` with ``edge_type = near_duplicate`` (hash + high similarity)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from config import Settings, get_settings
from models.domain import Page, PageGraphEdge, PageLink
from services.page_graph_content_similarity import (
    _IMPORTANT_TERMS_PER_PAGE,
    _MAX_SHARED_TERMS_IN_EVIDENCE,
    _SIMILARITY_ROUND_DECIMALS,
    _cosine_sparse,
    _important_term_ids,
    load_job_tfidf_context,
)

_INSERT_BATCH = 500
_FAR_FUTURE = datetime.max.replace(tzinfo=timezone.utc)


def _canonical_tuple(page: Page, inbound: int) -> tuple[Any, ...]:
    """Smaller tuple wins as canonical (tie-break rules)."""
    title = (page.title or "").strip()
    return (
        len(page.normalized_url),
        -inbound,
        0 if title else 1,
        -len(title),
        title,
        page.fetched_at is None,
        page.fetched_at or _FAR_FUTURE,
        page.id,
    )


def _pick_canonical(pages: list[Page], inbound_by_id: dict[int, int]) -> Page:
    return min(pages, key=lambda p: _canonical_tuple(p, inbound_by_id.get(p.id, 0)))


def _inbound_counts(session: Session, crawl_job_id: int, pages: list[Page]) -> dict[int, int]:
    norm_to_id = {p.normalized_url: p.id for p in pages}
    counts: dict[int, int] = defaultdict(int)
    rows = session.execute(
        select(PageLink.target_page_id, PageLink.target_normalized_url).where(
            PageLink.crawl_job_id == crawl_job_id,
        ),
    ).all()
    for tid, turl in rows:
        if tid is not None:
            counts[int(tid)] += 1
        else:
            pid = norm_to_id.get(turl)
            if pid is not None:
                counts[pid] += 1
    return dict(counts)


def _different_content_hash(a: Page, b: Page) -> bool:
    """True when we may add a similarity-based near-duplicate (exclude same-hash pairs)."""
    ha, hb = a.content_hash, b.content_hash
    if ha is not None and hb is not None and ha == hb:
        return False
    return True


def _high_similarity_evidence(
    *,
    shared_term_ids: list[int],
    term_label: dict[int, str],
    similarity: float,
) -> dict[str, Any]:
    labels = sorted({term_label[t] for t in shared_term_ids if t in term_label})[
        :_MAX_SHARED_TERMS_IN_EVIDENCE
    ]
    return {
        "kind": "high_similarity",
        "similarity": round(float(similarity), _SIMILARITY_ROUND_DECIMALS),
        "shared_terms": labels,
    }


def generate_near_duplicate_edges_for_job(
    session: Session,
    crawl_job_id: int,
    *,
    settings: Settings | None = None,
    min_similarity: float | None = None,
) -> int:
    """
    Insert ``near_duplicate`` edges: (1) exact ``content_hash`` groups, canonical → duplicate
    with weight 1.0; (2) optional high TF–IDF cosine pairs (different hash) with weight = cosine.
    Idempotent via ``ON CONFLICT DO NOTHING``.
    """
    cfg = settings or get_settings()
    min_sim = float(
        min_similarity if min_similarity is not None else cfg.graph_near_duplicate_min_score,
    )

    pages = list(session.scalars(select(Page).where(Page.crawl_job_id == crawl_job_id)).all())
    if not pages:
        return 0

    inbound_by_id = _inbound_counts(session, crawl_job_id, pages)
    page_by_id = {p.id: p for p in pages}

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
            .returning(PageGraphEdge.__table__.c.id)
        )
        res = session.execute(stmt)
        inserted_total += len(res.fetchall())
        batch.clear()

    # --- 1) Exact content_hash groups ---
    by_hash: dict[str, list[Page]] = defaultdict(list)
    for p in pages:
        if p.content_hash:
            by_hash[p.content_hash].append(p)

    for chash, group in by_hash.items():
        if len(group) < 2:
            continue
        canonical = _pick_canonical(group, inbound_by_id)
        for p in group:
            if p.id == canonical.id:
                continue
            batch.append(
                {
                    "crawl_job_id": crawl_job_id,
                    "source_page_id": canonical.id,
                    "target_page_id": p.id,
                    "edge_type": "near_duplicate",
                    "weight": 1.0,
                    "evidence": {"kind": "content_hash_match", "content_hash": chash},
                },
            )
            if len(batch) >= _INSERT_BATCH:
                flush()

    flush()

    # --- 2) High similarity (postings only), different content_hash ---
    ctx = load_job_tfidf_context(session, crawl_job_id)
    if ctx is not None:
        page_vec = ctx.page_vec
        page_norm = ctx.page_norm
        term_to_pages = ctx.term_to_pages
        term_label = ctx.term_label
        seen_pairs: set[tuple[int, int]] = set()

        for src in sorted(page_vec.keys()):
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

            for tgt in candidates:
                if tgt <= src:
                    continue
                pair_key = (src, tgt)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                p_src = page_by_id.get(src)
                p_tgt = page_by_id.get(tgt)
                if p_src is None or p_tgt is None:
                    continue
                if not _different_content_hash(p_src, p_tgt):
                    continue

                w_tgt = page_vec[tgt]
                n_tgt = page_norm[tgt]
                sim = _cosine_sparse(w_src, w_tgt, n_src, n_tgt)
                if sim < min_sim:
                    continue

                canonical = _pick_canonical([p_src, p_tgt], inbound_by_id)
                duplicate = p_tgt if canonical.id == p_src.id else p_src
                if canonical.id == duplicate.id:
                    continue

                shared_ids = sorted(set(w_src) & set(w_tgt))
                ev = _high_similarity_evidence(
                    shared_term_ids=shared_ids,
                    term_label=term_label,
                    similarity=sim,
                )
                batch.append(
                    {
                        "crawl_job_id": crawl_job_id,
                        "source_page_id": canonical.id,
                        "target_page_id": duplicate.id,
                        "edge_type": "near_duplicate",
                        "weight": float(sim),
                        "evidence": ev,
                    },
                )
                if len(batch) >= _INSERT_BATCH:
                    flush()

    flush()
    return inserted_total
