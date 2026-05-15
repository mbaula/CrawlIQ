"""Attach graph neighbors to search hits (same crawl job, undirected edges)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models.domain import Page, PageGraphEdge

from services.graph_edge_reason import format_graph_edge_reason

# Lower index = higher priority when picking one edge between the same page pair.
_EDGE_TYPE_PRIORITY: dict[str, int] = {
    "near_duplicate": 0,
    "link": 1,
    "url_hierarchy": 2,
    "content_similarity": 3,
    "semantic_similarity": 4,
    "co_ranked": 5,
    "shared_terms": 6,
    "manual": 7,
}


def _primary_edge(edges: list[PageGraphEdge]) -> PageGraphEdge:
    def sort_key(e: PageGraphEdge) -> tuple[int, float, int]:
        pr = _EDGE_TYPE_PRIORITY.get(e.edge_type, 99)
        return (pr, -float(e.weight), int(e.id))

    return min(edges, key=sort_key)


def attach_related_to_search_results(
    session: Session,
    *,
    crawl_job_id: int,
    result_rows: list[dict[str, Any]],
    related_limit: int,
) -> None:
    """
    Mutates each row in ``result_rows`` to add key ``related``: list of dicts with
    page_id, title, url, edge_type, strength, reason, also_related_by — sorted by
    strength desc, page_id asc, capped at ``related_limit`` per hit.

    When several edges connect the same hit and neighbor, the primary row uses the
    edge type with the best (lowest) priority in ``_EDGE_TYPE_PRIORITY``; ties use
    higher weight then lower ``page_graph_edges.id``. Other edge types for that pair
    are listed in ``also_related_by`` (sorted).
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

    pair_edges: dict[tuple[int, int], list[PageGraphEdge]] = defaultdict(list)
    for e in edges:
        s, t = int(e.source_page_id), int(e.target_page_id)
        if s in hit_set and t != s:
            pair_edges[(s, t)].append(e)
        if t in hit_set and s != t:
            pair_edges[(t, s)].append(e)

    by_hit: dict[int, list[tuple[int, float, str, Any, int, list[str]]]] = defaultdict(list)
    for (hit, neigh), lst in pair_edges.items():
        primary = _primary_edge(lst)
        w = float(primary.weight)
        et = primary.edge_type
        ev = primary.evidence
        eid = int(primary.id)
        other_types = sorted({e.edge_type for e in lst if int(e.id) != eid})
        by_hit[hit].append((neigh, w, et, ev, eid, other_types))

    all_neighbor_ids: set[int] = set()
    for lst in by_hit.values():
        for neigh, _w, _et, _ev, _eid, _o in lst:
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
        for neigh, w, et, ev, _eid, other_types in candidates:
            if len(related_out) >= related_limit:
                break
            p = page_by_id.get(neigh)
            if p is None:
                continue
            reason = format_graph_edge_reason(et, ev, w)
            related_out.append(
                {
                    "page_id": neigh,
                    "title": p.title,
                    "url": p.url,
                    "edge_type": et,
                    "strength": round(w, 6),
                    "reason": reason,
                    "also_related_by": other_types,
                },
            )
        row["related"] = related_out
