"""Attach graph neighbors to search hits (same crawl job, undirected edges)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models.domain import Page, PageGraphEdge

from services.search_related_reason import format_related_reason


def attach_related_to_search_results(
    session: Session,
    *,
    crawl_job_id: int,
    result_rows: list[dict[str, Any]],
    related_limit: int,
) -> None:
    """
    Mutates each row in ``result_rows`` to add key ``related``: list of dicts with
    page_id, title, url, edge_type, strength, reason — sorted by strength desc, page_id asc,
    capped at ``related_limit`` per hit (counting only neighbors with a ``pages`` row).
    Self-links are ignored. If multiple edges connect the same neighbor, the highest
    ``weight`` wins; ties break on lower ``page_graph_edges.id``.
    """
    if related_limit <= 0:
        for row in result_rows:
            row["related"] = []
        return

    hit_ids = [int(row["page_id"]) for row in result_rows]
    if not hit_ids:
        for row in result_rows:
            row["related"] = []
        return

    hit_set = frozenset(hit_ids)
    stmt = select(PageGraphEdge).where(
        PageGraphEdge.crawl_job_id == crawl_job_id,
        or_(
            PageGraphEdge.source_page_id.in_(hit_ids),
            PageGraphEdge.target_page_id.in_(hit_ids),
        ),
    )
    edges = list(session.scalars(stmt).all())

    # (hit_page_id, neighbor_page_id) -> (weight, edge_type, evidence, edge_id)
    best: dict[tuple[int, int], tuple[float, str, Any, int]] = {}

    def upsert_best(hit: int, neighbor: int, e: PageGraphEdge) -> None:
        if neighbor == hit:
            return
        key = (hit, neighbor)
        w = float(e.weight)
        eid = int(e.id)
        et = e.edge_type
        ev = e.evidence
        prev = best.get(key)
        if prev is None:
            best[key] = (w, et, ev, eid)
            return
        pw, _pet, _pev, peid = prev
        if w > pw or (w == pw and eid < peid):
            best[key] = (w, et, ev, eid)

    for e in edges:
        s, t = int(e.source_page_id), int(e.target_page_id)
        if s in hit_set:
            upsert_best(s, t, e)
        if t in hit_set:
            upsert_best(t, s, e)

    by_hit: dict[int, list[tuple[int, float, str, Any, int]]] = defaultdict(list)
    for (hit, neigh), (w, et, ev, eid) in best.items():
        by_hit[hit].append((neigh, w, et, ev, eid))

    all_neighbor_ids: set[int] = set()
    for lst in by_hit.values():
        for neigh, _w, _et, _ev, _eid in lst:
            all_neighbor_ids.add(neigh)

    page_by_id: dict[int, Page] = {}
    if all_neighbor_ids:
        pages = session.scalars(select(Page).where(Page.id.in_(sorted(all_neighbor_ids)))).all()
        page_by_id = {p.id: p for p in pages}

    for row in result_rows:
        hit = int(row["page_id"])
        candidates = by_hit.get(hit, [])
        candidates.sort(key=lambda x: (-x[1], x[0]))
        related_out: list[dict[str, Any]] = []
        for neigh, w, et, ev, eid in candidates:
            if len(related_out) >= related_limit:
                break
            p = page_by_id.get(neigh)
            if p is None:
                continue
            reason = format_related_reason(edge_type=et, evidence=ev, weight=w)
            related_out.append(
                {
                    "page_id": neigh,
                    "title": p.title,
                    "url": p.url,
                    "edge_type": et,
                    "strength": round(w, 6),
                    "reason": reason,
                },
            )
        row["related"] = related_out
