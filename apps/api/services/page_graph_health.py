"""Graph health dashboard aggregates (precomputed tables only; no graph recomputation)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session

from models.domain import Page, PageGraphCluster, PageGraphEdge, PageGraphMetric
from schemas.graph_health import (
    GraphHealthClusterRow,
    GraphHealthDuplicateClusterRead,
    GraphHealthDupNeighborRead,
    GraphHealthPageRow,
    GraphHealthRead,
    GraphHealthSummaryRead,
)

_TOP_PAGES = 15
_TOP_CLUSTERS = 12
_SMALL_CLUSTER_MAX = 3
_TOP_SMALL_CLUSTERS = 15
_TOP_DUP_CLUSTERS = 20
_MAX_DUP_NEIGHBORS = 12
_MAX_SAMPLE_URLS = 4


def build_graph_health_placeholder() -> GraphHealthRead:
    """No ``job_id`` — UI shows corpus selector."""
    return GraphHealthRead(
        job_id=None,
        message="Pass job_id to load graph health for a crawl job.",
    )


def build_graph_health_read(session: Session, *, crawl_job_id: int) -> GraphHealthRead:
    page_count = int(
        session.scalar(select(func.count()).select_from(Page).where(Page.crawl_job_id == crawl_job_id)) or 0,
    )
    edge_count = int(
        session.scalar(
            select(func.count()).select_from(PageGraphEdge).where(PageGraphEdge.crawl_job_id == crawl_job_id),
        )
        or 0,
    )
    metrics_count = int(
        session.scalar(
            select(func.count()).select_from(PageGraphMetric).where(PageGraphMetric.crawl_job_id == crawl_job_id),
        )
        or 0,
    )
    cluster_row_count = int(
        session.scalar(
            select(func.count()).select_from(PageGraphCluster).where(PageGraphCluster.crawl_job_id == crawl_job_id),
        )
        or 0,
    )
    distinct_cluster_ids = int(
        session.scalar(
            select(func.count(func.distinct(PageGraphCluster.cluster_id))).where(
                PageGraphCluster.crawl_job_id == crawl_job_id,
            ),
        )
        or 0,
    )

    use_metric_orphans = page_count > 0 and metrics_count == page_count
    orphan_warning: str | None = None
    if not use_metric_orphans and page_count > 0:
        orphan_warning = (
            "Graph metrics not computed for every page; orphan detection is edge-count based "
            "(no incident edges in page_graph_edges)."
        )

    orphan_rows: list[tuple[int, str | None, str]] = []
    if use_metric_orphans:
        ostmt = (
            select(Page.id, Page.title, Page.url)
            .join(
                PageGraphMetric,
                and_(PageGraphMetric.page_id == Page.id, PageGraphMetric.crawl_job_id == crawl_job_id),
            )
            .where(
                Page.crawl_job_id == crawl_job_id,
                PageGraphMetric.in_degree == 0,
                PageGraphMetric.out_degree == 0,
            )
            .order_by(Page.id.asc())
            .limit(_TOP_PAGES * 3)
        )
        orphan_rows = list(session.execute(ostmt).all())
    else:
        edge_exists = (
            select(PageGraphEdge.id)
            .where(
                PageGraphEdge.crawl_job_id == crawl_job_id,
                or_(
                    PageGraphEdge.source_page_id == Page.id,
                    PageGraphEdge.target_page_id == Page.id,
                ),
            )
            .limit(1)
            .correlate(Page)
            .exists()
        )
        ostmt = (
            select(Page.id, Page.title, Page.url)
            .where(Page.crawl_job_id == crawl_job_id, not_(edge_exists))
            .order_by(Page.id.asc())
            .limit(_TOP_PAGES * 3)
        )
        orphan_rows = list(session.execute(ostmt).all())
    orphan_count_total = len(orphan_rows)
    orphan_pages = [
        GraphHealthPageRow(page_id=int(r[0]), title=r[1], url=str(r[2])) for r in orphan_rows[:_TOP_PAGES]
    ]

    dup_canonical_stmt = (
        select(PageGraphEdge.source_page_id, func.count())
        .where(
            PageGraphEdge.crawl_job_id == crawl_job_id,
            PageGraphEdge.edge_type == "near_duplicate",
        )
        .group_by(PageGraphEdge.source_page_id)
        .order_by(func.count().desc())
        .limit(_TOP_DUP_CLUSTERS)
    )
    dup_canonical_rows = list(session.execute(dup_canonical_stmt).all())
    duplicate_cluster_count = len(dup_canonical_rows)

    canonical_ids = [int(r[0]) for r in dup_canonical_rows]
    dup_edges: list[PageGraphEdge] = []
    if canonical_ids:
        dup_edges = list(
            session.scalars(
                select(PageGraphEdge).where(
                    PageGraphEdge.crawl_job_id == crawl_job_id,
                    PageGraphEdge.edge_type == "near_duplicate",
                    PageGraphEdge.source_page_id.in_(canonical_ids),
                ),
            ).all(),
        )
    by_canon: dict[int, list[PageGraphEdge]] = defaultdict(list)
    for e in dup_edges:
        by_canon[int(e.source_page_id)].append(e)
    for lst in by_canon.values():
        lst.sort(key=lambda x: (float(x.weight), int(x.target_page_id)))

    dup_target_ids = sorted({int(e.target_page_id) for e in dup_edges})
    dup_page_by_id: dict[int, Page] = {}
    if dup_target_ids:
        for p in session.scalars(select(Page).where(Page.id.in_(dup_target_ids))).all():
            dup_page_by_id[int(p.id)] = p
    canon_page_by_id: dict[int, Page] = {}
    if canonical_ids:
        for p in session.scalars(select(Page).where(Page.id.in_(canonical_ids))).all():
            canon_page_by_id[int(p.id)] = p

    duplicate_clusters: list[GraphHealthDuplicateClusterRead] = []
    for cid, _cnt in dup_canonical_rows:
        cid = int(cid)
        canon = canon_page_by_id.get(cid)
        if canon is None:
            continue
        neighbors: list[GraphHealthDupNeighborRead] = []
        for e in by_canon.get(cid, [])[:_MAX_DUP_NEIGHBORS]:
            tp = dup_page_by_id.get(int(e.target_page_id))
            neighbors.append(
                GraphHealthDupNeighborRead(
                    page_id=int(e.target_page_id),
                    title=tp.title if tp else None,
                    url=tp.url if tp else "",
                    weight=float(e.weight),
                    evidence=e.evidence,
                ),
            )
        duplicate_clusters.append(
            GraphHealthDuplicateClusterRead(
                canonical_page_id=cid,
                canonical_title=canon.title,
                canonical_url=canon.url,
                duplicate_count=len(by_canon.get(cid, [])),
                duplicates=neighbors,
            ),
        )

    def _page_rows_from_metric_stmt(stmt) -> list[GraphHealthPageRow]:
        rows = list(session.execute(stmt).all())
        out: list[GraphHealthPageRow] = []
        for r in rows:
            out.append(
                GraphHealthPageRow(
                    page_id=int(r[0]),
                    title=r[1],
                    url=str(r[2]),
                    pagerank=float(r[3]) if r[3] is not None else None,
                    in_degree=int(r[4]) if r[4] is not None else None,
                    out_degree=int(r[5]) if r[5] is not None else None,
                ),
            )
        return out

    hub_stmt = (
        select(
            Page.id,
            Page.title,
            Page.url,
            PageGraphMetric.pagerank,
            PageGraphMetric.in_degree,
            PageGraphMetric.out_degree,
        )
        .join(PageGraphMetric, and_(PageGraphMetric.page_id == Page.id, PageGraphMetric.crawl_job_id == crawl_job_id))
        .where(Page.crawl_job_id == crawl_job_id)
        .order_by(PageGraphMetric.out_degree.desc(), Page.id.asc())
        .limit(_TOP_PAGES)
    )
    hub_pages = _page_rows_from_metric_stmt(hub_stmt)

    pr_stmt = (
        select(
            Page.id,
            Page.title,
            Page.url,
            PageGraphMetric.pagerank,
            PageGraphMetric.in_degree,
            PageGraphMetric.out_degree,
        )
        .join(PageGraphMetric, and_(PageGraphMetric.page_id == Page.id, PageGraphMetric.crawl_job_id == crawl_job_id))
        .where(Page.crawl_job_id == crawl_job_id, PageGraphMetric.pagerank.isnot(None))
        .order_by(PageGraphMetric.pagerank.desc().nulls_last(), Page.id.asc())
        .limit(_TOP_PAGES)
    )
    top_pagerank_pages = _page_rows_from_metric_stmt(pr_stmt)

    auth_by_pr = _page_rows_from_metric_stmt(
        select(
            Page.id,
            Page.title,
            Page.url,
            PageGraphMetric.pagerank,
            PageGraphMetric.in_degree,
            PageGraphMetric.out_degree,
        )
        .join(PageGraphMetric, and_(PageGraphMetric.page_id == Page.id, PageGraphMetric.crawl_job_id == crawl_job_id))
        .where(Page.crawl_job_id == crawl_job_id, PageGraphMetric.pagerank.isnot(None))
        .order_by(PageGraphMetric.pagerank.desc().nulls_last(), Page.id.asc())
        .limit(_TOP_PAGES),
    )
    auth_by_in = _page_rows_from_metric_stmt(
        select(
            Page.id,
            Page.title,
            Page.url,
            PageGraphMetric.pagerank,
            PageGraphMetric.in_degree,
            PageGraphMetric.out_degree,
        )
        .join(PageGraphMetric, and_(PageGraphMetric.page_id == Page.id, PageGraphMetric.crawl_job_id == crawl_job_id))
        .where(Page.crawl_job_id == crawl_job_id)
        .order_by(PageGraphMetric.in_degree.desc(), Page.id.asc())
        .limit(_TOP_PAGES),
    )
    seen_auth: set[int] = set()
    authority_pages: list[GraphHealthPageRow] = []
    for row in auth_by_pr + auth_by_in:
        if row.page_id in seen_auth:
            continue
        seen_auth.add(row.page_id)
        authority_pages.append(row)
        if len(authority_pages) >= _TOP_PAGES:
            break

    link_in_stmt = (
        select(
            Page.id,
            Page.title,
            Page.url,
            func.count().label("lc"),
        )
        .join(
            PageGraphEdge,
            and_(
                PageGraphEdge.target_page_id == Page.id,
                PageGraphEdge.crawl_job_id == crawl_job_id,
                PageGraphEdge.edge_type == "link",
            ),
        )
        .where(Page.crawl_job_id == crawl_job_id)
        .group_by(Page.id, Page.title, Page.url)
        .order_by(func.count().desc(), Page.id.asc())
        .limit(_TOP_PAGES)
    )
    most_linked_pages = [
        GraphHealthPageRow(
            page_id=int(r[0]),
            title=r[1],
            url=str(r[2]),
            link_in_count=int(r[3]),
        )
        for r in session.execute(link_in_stmt).all()
    ]

    cluster_sizes_stmt = (
        select(
            PageGraphCluster.cluster_id,
            func.count().label("member_count"),
            func.min(PageGraphCluster.page_id).label("rep_id"),
            func.min(PageGraphCluster.cluster_label).label("lab"),
        )
        .where(PageGraphCluster.crawl_job_id == crawl_job_id)
        .group_by(PageGraphCluster.cluster_id)
    )
    cluster_sizes = list(session.execute(cluster_sizes_stmt).all())
    cluster_sizes.sort(key=lambda x: (-int(x[1]), int(x[0])))

    largest_clusters: list[GraphHealthClusterRow] = []
    small_clusters: list[GraphHealthClusterRow] = []

    def _cluster_row(cluster_id: int, member_count: int, rep_id: int, lab: Any) -> GraphHealthClusterRow | None:
        rep = session.get(Page, rep_id)
        if rep is None or int(rep.crawl_job_id) != crawl_job_id:
            return None
        urls = list(
            session.scalars(
                select(Page.url)
                .join(PageGraphCluster, PageGraphCluster.page_id == Page.id)
                .where(
                    PageGraphCluster.crawl_job_id == crawl_job_id,
                    PageGraphCluster.cluster_id == cluster_id,
                )
                .order_by(Page.id.asc())
                .limit(_MAX_SAMPLE_URLS),
            ).all(),
        )
        return GraphHealthClusterRow(
            cluster_id=cluster_id,
            member_count=member_count,
            representative_page_id=int(rep.id),
            representative_title=rep.title,
            representative_url=rep.url,
            cluster_label=str(lab) if lab is not None else None,
            sample_urls=[str(u) for u in urls],
        )

    for row in cluster_sizes[:_TOP_CLUSTERS]:
        cid, mc, rid, lab = int(row[0]), int(row[1]), int(row[2]), row[3]
        cr = _cluster_row(cid, mc, rid, lab)
        if cr:
            largest_clusters.append(cr)

    small_candidates = [x for x in cluster_sizes if int(x[1]) <= _SMALL_CLUSTER_MAX and int(x[1]) >= 1]
    small_candidates.sort(key=lambda x: (int(x[1]), int(x[0])))
    for row in small_candidates[:_TOP_SMALL_CLUSTERS]:
        cid, mc, rid, lab = int(row[0]), int(row[1]), int(row[2]), row[3]
        cr = _cluster_row(cid, mc, rid, lab)
        if cr:
            small_clusters.append(cr)

    msg: str | None = None
    if page_count == 0:
        msg = "No pages in this crawl job yet."
    elif edge_count == 0:
        msg = "Graph edges have not been generated for this job (run graph edge jobs / backfill)."

    summary = GraphHealthSummaryRead(
        page_count=page_count,
        edge_count=edge_count,
        metrics_count=metrics_count,
        cluster_row_count=cluster_row_count,
        distinct_cluster_ids=distinct_cluster_ids,
        orphan_count=orphan_count_total,
        duplicate_cluster_count=duplicate_cluster_count,
        orphan_detection_warning=orphan_warning,
    )

    return GraphHealthRead(
        job_id=crawl_job_id,
        message=msg,
        summary=summary,
        top_pagerank_pages=top_pagerank_pages,
        hub_pages=hub_pages,
        authority_pages=authority_pages,
        orphan_pages=orphan_pages,
        largest_clusters=largest_clusters,
        small_clusters=small_clusters,
        duplicate_clusters=duplicate_clusters,
        most_linked_pages=most_linked_pages,
    )
