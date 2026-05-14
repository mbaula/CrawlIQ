"""Graph-enhanced search reranking (BM25 + PageRank + neighbors − duplicates)."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from config import Settings, get_settings
from models.domain import Page, PageGraphEdge, PageGraphMetric
from services.search_pages import _build_snippet, _strip_repeated_ws, execute_search_ranked_pages

# Linear blend weights (BM25 and graph signals are min–max normalized per query).
_W_BM25 = 1.0
_W_PAGERANK = 0.12
_W_NEIGHBOR = 0.18
_W_DUPLICATE = 0.25

# BM25 pool cap before neighbor expansion (safety on very large jobs).
_MAX_BM25_POOL = 5000


def _min_max_norm(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return {}
    xs = [v for v in values.values() if math.isfinite(v)]
    if not xs:
        return {k: 0.0 for k in values}
    lo, hi = min(xs), max(xs)
    if hi <= lo:
        return {k: 0.0 for k in values}
    return {k: (float(values[k]) - lo) / (hi - lo) for k in values}


def _shrink_candidate_set(
    candidates: set[int],
    *,
    seed_ids: frozenset[int],
    bm25_by_id: dict[int, float],
    max_size: int,
) -> set[int]:
    c = set(candidates)
    while len(c) > max_size:
        removable = [p for p in c if p not in seed_ids]
        if not removable:
            break
        removable.sort(
            key=lambda pid: (
                1 if pid in bm25_by_id else 0,
                bm25_by_id.get(pid, 0.0),
                pid,
            ),
        )
        c.discard(removable[0])
    return c


def search_indexed_pages_graph_enhanced(
    session: Session,
    *,
    raw_query: str,
    crawl_job_id: int,
    result_limit: int,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """
    BM25 first, expand candidates with 1-hop ``page_graph_edges``, rerank, return top ``result_limit``.

    Each row includes ``score`` (final rerank score), ``score_components``, and ``score_explanation``.
    """
    cfg = settings or get_settings()
    seed_limit = int(cfg.graph_rerank_seed_limit)
    max_candidates = int(cfg.graph_rerank_max_candidates)

    pool_cap = min(_MAX_BM25_POOL, max(max_candidates * 3, seed_limit * 20))
    ranked_bm25, _stats = execute_search_ranked_pages(
        session,
        raw_query=raw_query,
        crawl_job_id=crawl_job_id,
        max_ranked=pool_cap,
    )
    if not ranked_bm25:
        return []

    bm25_by_id: dict[int, float] = {r.page_id: float(r.score) for r in ranked_bm25}
    matched_by_id: dict[int, frozenset[str]] = {r.page_id: r.matched_terms for r in ranked_bm25}

    seeds = ranked_bm25[:seed_limit]
    seed_ids = frozenset(s.page_id for s in seeds)

    b_ids = {r.page_id for r in ranked_bm25[:max_candidates]}
    if not b_ids:
        return []

    stmt_edges = select(PageGraphEdge.source_page_id, PageGraphEdge.target_page_id, PageGraphEdge.weight).where(
        PageGraphEdge.crawl_job_id == crawl_job_id,
        or_(
            PageGraphEdge.source_page_id.in_(b_ids),
            PageGraphEdge.target_page_id.in_(b_ids),
        ),
    )
    c: set[int] = set(b_ids)
    for src, tgt, _w in session.execute(stmt_edges):
        s, t = int(src), int(tgt)
        if s in b_ids or t in b_ids:
            c.add(s)
            c.add(t)

    c = _shrink_candidate_set(c, seed_ids=seed_ids, bm25_by_id=bm25_by_id, max_size=max_candidates)

    seed_bm25 = {s.page_id: float(s.score) for s in seeds}
    undirected_w: dict[tuple[int, int], float] = {}
    stmt_e2 = select(PageGraphEdge.source_page_id, PageGraphEdge.target_page_id, PageGraphEdge.weight).where(
        PageGraphEdge.crawl_job_id == crawl_job_id,
        or_(
            PageGraphEdge.source_page_id.in_(c),
            PageGraphEdge.target_page_id.in_(c),
        ),
    )
    for src, tgt, w in session.execute(stmt_e2):
        a, b = int(src), int(tgt)
        if a > b:
            a, b = b, a
        key = (a, b)
        undirected_w[key] = max(undirected_w.get(key, 0.0), float(w))

    neighbor_boost_raw: dict[int, float] = {pid: 0.0 for pid in c}
    for sid in seed_bm25:
        sbm = max(seed_bm25[sid], 1e-9)
        for pid in c:
            if pid == sid:
                continue
            a, b = (pid, sid) if pid < sid else (sid, pid)
            w = undirected_w.get((a, b))
            if w is not None:
                neighbor_boost_raw[pid] += w * math.log1p(sbm)

    dup_raw: dict[int, float] = defaultdict(float)
    stmt_nd = select(PageGraphEdge.source_page_id, PageGraphEdge.target_page_id, PageGraphEdge.weight).where(
        PageGraphEdge.crawl_job_id == crawl_job_id,
        PageGraphEdge.edge_type == "near_duplicate",
        PageGraphEdge.source_page_id.in_(c),
        PageGraphEdge.target_page_id.in_(c),
    )
    for src, tgt, w in session.execute(stmt_nd):
        a, b = int(src), int(tgt)
        sa, sb = bm25_by_id.get(a, 0.0), bm25_by_id.get(b, 0.0)
        if sa < sb:
            dup_raw[a] += float(w)
        elif sb < sa:
            dup_raw[b] += float(w)
        else:
            dup_raw[max(a, b)] += float(w) * 0.5

    rows_p = session.scalars(select(Page).where(Page.id.in_(sorted(c)))).all()
    chash_by_id: dict[int, str | None] = {p.id: p.content_hash for p in rows_p}
    hash_groups: dict[str, list[int]] = defaultdict(list)
    for p in rows_p:
        if p.content_hash:
            hash_groups[p.content_hash].append(p.id)
    for _h, ids in hash_groups.items():
        if len(ids) < 2:
            continue
        best = max(ids, key=lambda i: (bm25_by_id.get(i, 0.0), -i))
        for i in ids:
            if i != best:
                dup_raw[i] += 1.0

    bm25_norm_map = _min_max_norm({pid: bm25_by_id.get(pid, 0.0) for pid in c})
    pr_vals: dict[int, float] = {}
    mrows = session.scalars(
        select(PageGraphMetric).where(
            PageGraphMetric.crawl_job_id == crawl_job_id,
            PageGraphMetric.page_id.in_(c),
        ),
    ).all()
    for m in mrows:
        if m.pagerank is not None:
            pr_vals[m.page_id] = float(m.pagerank)
    pr_norm_map = _min_max_norm(pr_vals) if pr_vals else {}
    nb_norm_map = _min_max_norm({pid: neighbor_boost_raw.get(pid, 0.0) for pid in c})
    dup_full = {pid: float(dup_raw.get(pid, 0.0)) for pid in c}
    dup_norm_map = _min_max_norm(dup_full)

    scored: list[tuple[int, float, dict[str, Any]]] = []
    for pid in c:
        br = bm25_by_id.get(pid, 0.0)
        bn = bm25_norm_map.get(pid, 0.0)
        prn = pr_norm_map.get(pid, 0.0) if pr_vals else 0.0
        nbr = neighbor_boost_raw.get(pid, 0.0)
        nn = nb_norm_map.get(pid, 0.0)
        dr = dup_raw.get(pid, 0.0)
        dn = dup_norm_map.get(pid, 0.0)
        final = _W_BM25 * bn + _W_PAGERANK * prn + _W_NEIGHBOR * nn - _W_DUPLICATE * dn
        components = {
            "bm25_raw": round(br, 6),
            "bm25_norm": round(bn, 6),
            "pagerank_norm": round(prn, 6),
            "neighbor_boost_raw": round(nbr, 6),
            "neighbor_boost_norm": round(nn, 6),
            "duplicate_penalty_raw": round(dr, 6),
            "duplicate_penalty_norm": round(dn, 6),
            "final_score": round(final, 6),
        }
        expl = (
            f"final={final:.4f} = {_W_BM25}×bm25_norm({bn:.3f}) + {_W_PAGERANK}×PR_norm({prn:.3f}) "
            f"+ {_W_NEIGHBOR}×neighbor_norm({nn:.3f}) − {_W_DUPLICATE}×dup_norm({dn:.3f}) "
            f"[raw BM25 {br:.4f}]"
        )
        scored.append((pid, final, {"components": components, "explanation": expl}))

    scored.sort(key=lambda x: (-x[1], x[0]))
    top = scored[:result_limit]

    page_by_id = {p.id: p for p in rows_p}
    out: list[dict[str, Any]] = []
    for pid, final, meta in top:
        page = page_by_id.get(pid)
        if page is None:
            continue
        terms = matched_by_id.get(pid, frozenset())
        matched = sorted(terms)
        snippet = _strip_repeated_ws(
            _build_snippet(
                title=page.title,
                body=page.extracted_text,
                highlight_terms=terms,
            ),
        )
        out.append(
            {
                "page_id": int(page.id),
                "title": page.title,
                "url": page.url,
                "score": round(float(final), 6),
                "snippet": snippet,
                "matched_terms": matched,
                "score_components": meta["components"],
                "score_explanation": meta["explanation"],
            },
        )

    return out
