"""Read-only graph queries: bounded BFS, induced subgraphs, stats, clusters."""

from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from models.domain import (
    CrawlJob,
    Page,
    PageGraphCluster,
    PageGraphEdge,
    PageGraphMetric,
)
from schemas.graph import (
    GraphClusterRowRead,
    GraphClustersRead,
    GraphEdgeRead,
    GraphEdgeTypeCountRead,
    GraphNodeMetricsRead,
    GraphNodeRead,
    GraphStatsRead,
    GraphSubgraphRead,
)


def crawl_job_exists(session: Session, crawl_job_id: int) -> bool:
    return session.get(CrawlJob, crawl_job_id) is not None


def get_page_in_job(session: Session, crawl_job_id: int, page_id: int) -> Page | None:
    return session.scalar(
        select(Page).where(
            and_(
                Page.id == page_id,
                Page.crawl_job_id == crawl_job_id,
            ),
        ),
    )


def bounded_bfs_page_ids(
    session: Session,
    *,
    crawl_job_id: int,
    center_page_id: int,
    radius: int,
    max_nodes: int,
) -> list[int]:
    """
    Undirected layered BFS from ``center_page_id`` within ``page_graph_edges`` for the job.

    Returns sorted page ids (always includes ``center_page_id`` when that page exists).
    """
    visited: dict[int, int] = {center_page_id: 0}
    frontier: set[int] = {center_page_id}

    for hop in range(radius):
        if len(visited) >= max_nodes:
            break
        if not frontier:
            break

        stmt = (
            select(PageGraphEdge.source_page_id, PageGraphEdge.target_page_id)
            .where(
                PageGraphEdge.crawl_job_id == crawl_job_id,
                or_(
                    PageGraphEdge.source_page_id.in_(frontier),
                    PageGraphEdge.target_page_id.in_(frontier),
                ),
            )
        )
        rows = session.execute(stmt).all()

        candidates: list[int] = []
        seen_cand: set[int] = set()
        for src, tgt in rows:
            if src in frontier and tgt not in visited:
                if tgt not in seen_cand:
                    seen_cand.add(tgt)
                    candidates.append(tgt)
            if tgt in frontier and src not in visited:
                if src not in seen_cand:
                    seen_cand.add(src)
                    candidates.append(src)
        candidates.sort()

        next_frontier: set[int] = set()
        for v in candidates:
            if len(visited) >= max_nodes:
                break
            visited[v] = hop + 1
            next_frontier.add(v)
        if len(visited) >= max_nodes:
            break
        frontier = next_frontier
        if not frontier:
            break

    return sorted(visited.keys())


def load_induced_edges(
    session: Session,
    *,
    crawl_job_id: int,
    page_ids: list[int],
) -> list[PageGraphEdge]:
    if not page_ids:
        return []
    stmt = (
        select(PageGraphEdge)
        .where(
            PageGraphEdge.crawl_job_id == crawl_job_id,
            PageGraphEdge.source_page_id.in_(page_ids),
            PageGraphEdge.target_page_id.in_(page_ids),
        )
        .order_by(
            PageGraphEdge.source_page_id,
            PageGraphEdge.target_page_id,
            PageGraphEdge.edge_type,
        )
    )
    return list(session.scalars(stmt).all())


def load_graph_stats(session: Session, *, crawl_job_id: int) -> dict:
    page_count = int(
        session.scalar(
            select(func.count()).select_from(Page).where(Page.crawl_job_id == crawl_job_id),
        )
        or 0,
    )
    edge_count = int(
        session.scalar(
            select(func.count())
            .select_from(PageGraphEdge)
            .where(PageGraphEdge.crawl_job_id == crawl_job_id),
        )
        or 0,
    )

    type_rows = session.execute(
        select(PageGraphEdge.edge_type, func.count())
        .where(PageGraphEdge.crawl_job_id == crawl_job_id)
        .group_by(PageGraphEdge.edge_type)
        .order_by(PageGraphEdge.edge_type),
    ).all()

    metrics_count = int(
        session.scalar(
            select(func.count())
            .select_from(PageGraphMetric)
            .where(PageGraphMetric.crawl_job_id == crawl_job_id),
        )
        or 0,
    )
    cluster_rows = int(
        session.scalar(
            select(func.count())
            .select_from(PageGraphCluster)
            .where(PageGraphCluster.crawl_job_id == crawl_job_id),
        )
        or 0,
    )
    distinct_clusters = int(
        session.scalar(
            select(func.count(func.distinct(PageGraphCluster.cluster_id))).where(
                PageGraphCluster.crawl_job_id == crawl_job_id,
            ),
        )
        or 0,
    )

    return {
        "page_count": page_count,
        "edge_count": edge_count,
        "edge_counts_by_type": [{"edge_type": str(et), "count": int(c)} for et, c in type_rows],
        "page_graph_metrics_count": metrics_count,
        "page_graph_cluster_rows": cluster_rows,
        "distinct_cluster_ids": distinct_clusters,
    }


def load_cluster_page_rows(
    session: Session,
    *,
    crawl_job_id: int,
    limit: int,
    offset: int,
) -> tuple[list[tuple[int, int, str | None]], int]:
    total = int(
        session.scalar(
            select(func.count()).select_from(PageGraphCluster).where(
                PageGraphCluster.crawl_job_id == crawl_job_id,
            ),
        )
        or 0,
    )
    stmt = (
        select(PageGraphCluster.page_id, PageGraphCluster.cluster_id, PageGraphCluster.cluster_label)
        .where(PageGraphCluster.crawl_job_id == crawl_job_id)
        .order_by(PageGraphCluster.cluster_id, PageGraphCluster.page_id)
        .offset(offset)
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    return [(int(r[0]), int(r[1]), r[2]) for r in rows], total


def build_subgraph_read(
    session: Session,
    *,
    crawl_job_id: int,
    center_page_id: int,
    radius: int,
    max_nodes: int,
) -> GraphSubgraphRead:
    page_ids = bounded_bfs_page_ids(
        session,
        crawl_job_id=crawl_job_id,
        center_page_id=center_page_id,
        radius=radius,
        max_nodes=max_nodes,
    )
    edge_rows = load_induced_edges(session, crawl_job_id=crawl_job_id, page_ids=page_ids)

    metrics_by_page: dict[int, PageGraphMetric] = {}
    if page_ids:
        mrows = session.scalars(
            select(PageGraphMetric).where(
                PageGraphMetric.crawl_job_id == crawl_job_id,
                PageGraphMetric.page_id.in_(page_ids),
            ),
        ).all()
        metrics_by_page = {m.page_id: m for m in mrows}

    cluster_by_page: dict[int, int] = {}
    if page_ids:
        crows = session.execute(
            select(PageGraphCluster.page_id, PageGraphCluster.cluster_id).where(
                PageGraphCluster.crawl_job_id == crawl_job_id,
                PageGraphCluster.page_id.in_(page_ids),
            ),
        ).all()
        cluster_by_page = {int(r[0]): int(r[1]) for r in crows}

    pages = []
    if page_ids:
        pages = list(
            session.scalars(
                select(Page)
                .where(
                    Page.crawl_job_id == crawl_job_id,
                    Page.id.in_(page_ids),
                )
                .order_by(Page.id),
            ).all(),
        )

    nodes: list[GraphNodeRead] = []
    for p in pages:
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
        nodes.append(
            GraphNodeRead(
                page_id=p.id,
                title=p.title,
                url=p.url,
                normalized_url=p.normalized_url,
                depth=p.depth,
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
        )
        for e in edge_rows
    ]

    return GraphSubgraphRead(
        crawl_job_id=crawl_job_id,
        center_page_id=center_page_id,
        radius=radius,
        max_nodes=max_nodes,
        nodes=nodes,
        edges=edges,
    )


def build_graph_stats_read(session: Session, *, crawl_job_id: int) -> GraphStatsRead:
    raw = load_graph_stats(session, crawl_job_id=crawl_job_id)
    return GraphStatsRead(
        crawl_job_id=crawl_job_id,
        page_count=raw["page_count"],
        edge_count=raw["edge_count"],
        edge_counts_by_type=[GraphEdgeTypeCountRead(**x) for x in raw["edge_counts_by_type"]],
        page_graph_metrics_count=raw["page_graph_metrics_count"],
        page_graph_cluster_rows=raw["page_graph_cluster_rows"],
        distinct_cluster_ids=raw["distinct_cluster_ids"],
    )


def build_clusters_read(
    session: Session,
    *,
    crawl_job_id: int,
    limit: int,
    offset: int,
) -> GraphClustersRead:
    rows, total = load_cluster_page_rows(session, crawl_job_id=crawl_job_id, limit=limit, offset=offset)
    items = [
        GraphClusterRowRead(page_id=pid, cluster_id=cid, cluster_label=lab) for pid, cid, lab in rows
    ]
    return GraphClustersRead(
        crawl_job_id=crawl_job_id,
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
