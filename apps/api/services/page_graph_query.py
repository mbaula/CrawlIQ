"""Query-centered graph context (GET /graph/query, Sprint 11)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from config import Settings
from models.domain import CrawlJob, Page, PageGraphCluster, PageGraphEdge, PageGraphMetric
from schemas.graph import (
    GraphEdgeRead,
    GraphNodeMetricsRead,
    GraphQueryNodeRead,
    GraphQueryNodeRole,
    GraphQueryRead,
    GraphQuerySelectedJobRead,
)
from services.graph_edge_reason import format_graph_edge_reason
from services.page_graph_read import (
    GRAPH_QUERY_DEFAULT_EXPANSION_EDGE_TYPES,
    bounded_bfs_page_ids_multi_center,
    dedupe_seeds_cap_max_nodes,
    load_induced_edges,
)
from services.search_pages import execute_search_ranked_pages


@dataclass(frozen=True)
class _JobPoolStats:
    crawl_job_id: int
    total_bm25_score: float
    hit_count: int
    created_at: object


def _select_best_job(stats: list[_JobPoolStats]) -> _JobPoolStats | None:
    if not stats:
        return None
    return max(
        stats,
        key=lambda s: (s.total_bm25_score, s.hit_count, s.created_at, s.crawl_job_id),
    )


def _near_duplicate_neighbors_of_seeds(
    session: Session,
    *,
    crawl_job_id: int,
    seed_ids: set[int],
    page_ids: list[int],
) -> set[int]:
    """Non-seed pages in ``page_ids`` linked by ``near_duplicate`` to any seed."""
    if not seed_ids or not page_ids:
        return set()
    pid_set = set(page_ids)
    stmt = (
        select(PageGraphEdge.source_page_id, PageGraphEdge.target_page_id)
        .where(
            PageGraphEdge.crawl_job_id == crawl_job_id,
            PageGraphEdge.edge_type == "near_duplicate",
            or_(
                and_(
                    PageGraphEdge.source_page_id.in_(seed_ids),
                    PageGraphEdge.target_page_id.in_(pid_set),
                ),
                and_(
                    PageGraphEdge.target_page_id.in_(seed_ids),
                    PageGraphEdge.source_page_id.in_(pid_set),
                ),
            ),
        )
    )
    dup: set[int] = set()
    for src, tgt in session.execute(stmt):
        a, b = int(src), int(tgt)
        if a in seed_ids and b not in seed_ids:
            dup.add(b)
        if b in seed_ids and a not in seed_ids:
            dup.add(a)
    return dup


def build_graph_query_read(
    session: Session,
    *,
    raw_query: str,
    explicit_job_id: int | None,
    max_seed_pages: int,
    radius: int,
    max_nodes: int,
    settings: Settings,
) -> GraphQueryRead:
    expansion_types = sorted(GRAPH_QUERY_DEFAULT_EXPANSION_EDGE_TYPES)
    hit_limit = int(settings.graph_query_global_hit_limit)

    crawl_scope: int | None = explicit_job_id
    ranked_pages, _corpus = execute_search_ranked_pages(
        session,
        raw_query=raw_query,
        crawl_job_id=crawl_scope,
        max_ranked=hit_limit,
    )

    if not ranked_pages:
        return GraphQueryRead(
            query=raw_query,
            message="No indexed pages matched this query.",
            global_hit_limit=hit_limit,
            max_seed_pages=max_seed_pages,
            radius=radius,
            max_nodes=max_nodes,
            expansion_edge_types=expansion_types,
            selected_job=None,
            seed_page_ids=[],
            nodes=[],
            edges=[],
        )

    page_ids_ranked = [rp.page_id for rp in ranked_pages]
    pages = list(
        session.scalars(select(Page).where(Page.id.in_(page_ids_ranked))).all(),
    )
    page_by_id = {p.id: p for p in pages}

    ranked_pairs: list[tuple[int, float]] = []
    for rp in ranked_pages:
        if rp.page_id in page_by_id:
            ranked_pairs.append((rp.page_id, float(rp.score)))

    page_job_by_id = {p.id: int(p.crawl_job_id) for p in pages}

    if explicit_job_id is not None:
        selected_id = explicit_job_id
        pool_for_job = [(pid, sc) for pid, sc in ranked_pairs if page_job_by_id.get(pid) == selected_id]
        total_score = sum(sc for _pid, sc in pool_for_job)
        hit_ct = len(pool_for_job)
        selected_job = GraphQuerySelectedJobRead(
            crawl_job_id=selected_id,
            selection_mode="explicit",
            total_bm25_score=total_score,
            hit_count=hit_ct,
            message="Crawl job was supplied explicitly; BM25 pool is scoped to this job only.",
        )
    else:
        totals: dict[int, float] = {}
        counts: dict[int, int] = {}
        for pid, score in ranked_pairs:
            jid = page_job_by_id.get(pid)
            if jid is None:
                continue
            totals[jid] = totals.get(jid, 0.0) + score
            counts[jid] = counts.get(jid, 0) + 1

        job_ids = sorted(totals.keys())
        job_rows = list(session.scalars(select(CrawlJob).where(CrawlJob.id.in_(job_ids))).all())
        stats = [
            _JobPoolStats(
                crawl_job_id=j.id,
                total_bm25_score=totals[j.id],
                hit_count=counts[j.id],
                created_at=j.created_at,
            )
            for j in job_rows
        ]
        best = _select_best_job(stats)
        if best is None:
            return GraphQueryRead(
                query=raw_query,
                message="No indexed pages matched this query.",
                global_hit_limit=hit_limit,
                max_seed_pages=max_seed_pages,
                radius=radius,
                max_nodes=max_nodes,
                expansion_edge_types=expansion_types,
                selected_job=None,
                seed_page_ids=[],
                nodes=[],
                edges=[],
            )
        selected_id = best.crawl_job_id
        selected_job = GraphQuerySelectedJobRead(
            crawl_job_id=selected_id,
            selection_mode="auto",
            total_bm25_score=best.total_bm25_score,
            hit_count=best.hit_count,
            message=(
                "Auto-selected crawl job from the global BM25 hit pool using: "
                "highest total raw BM25 score, then hit count, then newest job, then highest job id."
            ),
        )

    seed_source = [rp for rp in ranked_pages if page_job_by_id.get(rp.page_id) == selected_id]
    seeds_ranked = [rp.page_id for rp in seed_source[:max_seed_pages]]
    score_by_seed = {rp.page_id: float(rp.score) for rp in seed_source[:max_seed_pages]}

    if not seeds_ranked:
        return GraphQueryRead(
            query=raw_query,
            message="No hits for the selected crawl job in the BM25 pool.",
            global_hit_limit=hit_limit,
            max_seed_pages=max_seed_pages,
            radius=radius,
            max_nodes=max_nodes,
            expansion_edge_types=expansion_types,
            selected_job=selected_job,
            seed_page_ids=[],
            nodes=[],
            edges=[],
        )

    seeds_for_bfs = dedupe_seeds_cap_max_nodes(seeds_ranked, max_nodes)

    page_ids = bounded_bfs_page_ids_multi_center(
        session,
        crawl_job_id=selected_id,
        seed_page_ids=seeds_ranked,
        radius=radius,
        max_nodes=max_nodes,
        expansion_edge_types=GRAPH_QUERY_DEFAULT_EXPANSION_EDGE_TYPES,
    )

    edge_rows = load_induced_edges(session, crawl_job_id=selected_id, page_ids=page_ids)

    metrics_by_page: dict[int, PageGraphMetric] = {}
    if page_ids:
        mrows = session.scalars(
            select(PageGraphMetric).where(
                PageGraphMetric.crawl_job_id == selected_id,
                PageGraphMetric.page_id.in_(page_ids),
            ),
        ).all()
        metrics_by_page = {m.page_id: m for m in mrows}

    cluster_by_page: dict[int, int] = {}
    if page_ids:
        crows = session.execute(
            select(PageGraphCluster.page_id, PageGraphCluster.cluster_id).where(
                PageGraphCluster.crawl_job_id == selected_id,
                PageGraphCluster.page_id.in_(page_ids),
            ),
        ).all()
        cluster_by_page = {int(r[0]): int(r[1]) for r in crows}

    pages_in_graph = list(
        session.scalars(
            select(Page)
            .where(
                Page.crawl_job_id == selected_id,
                Page.id.in_(page_ids),
            )
            .order_by(Page.id),
        ).all(),
    )

    seed_set = set(seeds_for_bfs)
    dup_marked = _near_duplicate_neighbors_of_seeds(
        session,
        crawl_job_id=selected_id,
        seed_ids=seed_set,
        page_ids=page_ids,
    )

    nodes: list[GraphQueryNodeRead] = []
    for p in pages_in_graph:
        m = metrics_by_page.get(p.id)
        metrics: GraphNodeMetricsRead | None = None
        if m is not None:
            metrics = GraphNodeMetricsRead(
                pagerank=m.pagerank,
                in_degree=m.in_degree,
                out_degree=m.out_degree,
                betweenness=m.betweenness,
                closeness=m.closeness,
            )
        role: GraphQueryNodeRole
        if p.id in seed_set:
            role = "query_match"
            bm25 = score_by_seed.get(p.id)
        elif p.id in dup_marked:
            role = "duplicate"
            bm25 = None
        else:
            role = "related_neighbor"
            bm25 = None

        nodes.append(
            GraphQueryNodeRead(
                page_id=p.id,
                title=p.title,
                url=p.url,
                normalized_url=p.normalized_url,
                depth=p.depth,
                role=role,
                bm25_score=bm25,
                metrics=metrics,
                cluster_id=cluster_by_page.get(p.id),
            ),
        )

    edges = [
        GraphEdgeRead(
            edge_id=e.id,
            source_page_id=e.source_page_id,
            target_page_id=e.target_page_id,
            edge_type=e.edge_type,
            weight=float(e.weight),
            evidence=e.evidence,
            reason=format_graph_edge_reason(e.edge_type, e.evidence, float(e.weight)),
        )
        for e in edge_rows
    ]

    return GraphQueryRead(
        query=raw_query,
        message=None,
        global_hit_limit=hit_limit,
        max_seed_pages=max_seed_pages,
        radius=radius,
        max_nodes=max_nodes,
        expansion_edge_types=expansion_types,
        selected_job=selected_job,
        seed_page_ids=seeds_for_bfs,
        nodes=nodes,
        edges=edges,
    )
