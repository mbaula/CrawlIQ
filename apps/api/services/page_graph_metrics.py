"""Compute ``page_graph_metrics`` and ``page_graph_clusters`` (PageRank, degrees, WCC, betweenness)."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from config import Settings, get_settings
from models.domain import Page, PageGraphCluster, PageGraphEdge, PageGraphMetric

_METRICS_EDGE_TYPES = frozenset({"link", "url_hierarchy"})
_PAGERANK_DAMPING = 0.85
_PAGERANK_MAX_ITER = 500
_PAGERANK_TOL = 1e-12


@dataclass(frozen=True)
class GraphMetricsComputeResult:
    pages_count: int
    edges_used: int
    pagerank_iterations: int
    weak_components_count: int
    betweenness_computed: bool


def _union_find(nodes: list[int], undirected_pairs: list[tuple[int, int]]) -> dict[int, int]:
    """Disjoint-set with min-id roots (``cluster_id`` = smallest ``page.id`` in component)."""
    parent = {n: n for n in nodes}

    def find(x: int) -> int:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: int, b: int) -> None:
        pa, pb = find(a), find(b)
        if pa == pb:
            return
        if pa < pb:
            parent[pb] = pa
        else:
            parent[pa] = pb

    for u, v in undirected_pairs:
        union(u, v)
    return {n: find(n) for n in nodes}


def _pagerank_directed_weighted(
    nodes: list[int],
    merged_out: dict[int, dict[int, float]],
    out_sum: dict[int, float],
) -> tuple[dict[int, float], int]:
    """Power iteration; ``merged_out[u][v]`` summed weights ``u -> v``."""
    n = len(nodes)
    if n == 0:
        return {}, 0
    idx_set = set(nodes)
    d = _PAGERANK_DAMPING
    teleport = (1.0 - d) / n
    rank = {u: 1.0 / n for u in nodes}
    iters = 0
    for _ in range(_PAGERANK_MAX_ITER):
        iters += 1
        new_rank = {u: teleport for u in nodes}
        dangling_mass = 0.0
        for u in nodes:
            s = out_sum.get(u, 0.0)
            ru = rank[u]
            if s <= 0.0:
                dangling_mass += d * ru
            else:
                row = merged_out.get(u)
                if not row:
                    dangling_mass += d * ru
                else:
                    inv = d * ru / s
                    for v, w in sorted(row.items()):
                        if v in idx_set:
                            new_rank[v] += inv * w
        if dangling_mass > 0.0:
            add = dangling_mass / n
            for v in nodes:
                new_rank[v] += add
        delta = max(abs(new_rank[u] - rank[u]) for u in nodes)
        rank = new_rank
        if delta < _PAGERANK_TOL:
            break
    return rank, iters


def _brandes_betweenness_undirected(
    nodes: list[int],
    adj: dict[int, set[int]],
) -> dict[int, float]:
    """Unweighted undirected Brandes; ``adj`` symmetric neighbors."""
    C = {v: 0.0 for v in nodes}
    for s in nodes:
        S: list[int] = []
        P = {w: list[int]() for w in nodes}
        sigma = {w: 0.0 for w in nodes}
        sigma[s] = 1.0
        dist = {w: -1 for w in nodes}
        dist[s] = 0
        Q: deque[int] = deque([s])
        while Q:
            v = Q.popleft()
            S.append(v)
            for w in sorted(adj.get(v, ())):
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    Q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    P[w].append(v)
        delta = {w: 0.0 for w in nodes}
        while S:
            w = S.pop()
            for v in P[w]:
                sw = sigma[w]
                if sw > 0.0:
                    delta[v] += (sigma[v] / sw) * (1.0 + delta[w])
            if w != s:
                C[w] += delta[w]
    for v in nodes:
        C[v] /= 2.0
    return C


def compute_graph_metrics_for_job(
    session: Session,
    crawl_job_id: int,
    *,
    settings: Settings | None = None,
    betweenness_max_pages: int | None = None,
) -> GraphMetricsComputeResult:
    """
    Rebuild ``page_graph_metrics`` and ``page_graph_clusters`` for one job.

    Uses ``link`` and ``url_hierarchy`` edges only. Deletes prior rows for the job
    then inserts one metric row and one cluster row per page (including isolates).
    """
    cfg = settings or get_settings()
    cap = int(
        betweenness_max_pages
        if betweenness_max_pages is not None
        else cfg.graph_metrics_betweenness_max_pages,
    )

    page_ids = list(
        session.scalars(
            select(Page.id).where(Page.crawl_job_id == crawl_job_id).order_by(Page.id.asc()),
        ).all(),
    )
    n_pages = len(page_ids)
    if n_pages == 0:
        session.execute(delete(PageGraphMetric).where(PageGraphMetric.crawl_job_id == crawl_job_id))
        session.execute(delete(PageGraphCluster).where(PageGraphCluster.crawl_job_id == crawl_job_id))
        return GraphMetricsComputeResult(
            pages_count=0,
            edges_used=0,
            pagerank_iterations=0,
            weak_components_count=0,
            betweenness_computed=False,
        )

    edge_rows = session.execute(
        select(PageGraphEdge.source_page_id, PageGraphEdge.target_page_id, PageGraphEdge.weight).where(
            PageGraphEdge.crawl_job_id == crawl_job_id,
            PageGraphEdge.edge_type.in_(_METRICS_EDGE_TYPES),
        ),
    ).all()

    in_deg = {p: 0 for p in page_ids}
    out_deg = {p: 0 for p in page_ids}
    merged_out: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    undirected_pairs: list[tuple[int, int]] = []
    adj_undir: dict[int, set[int]] = {p: set() for p in page_ids}
    pid_set = set(page_ids)

    edges_used = 0
    for su, tu, w in edge_rows:
        if su not in pid_set or tu not in pid_set or su == tu:
            continue
        wt = float(w)
        if wt < 0.0:
            wt = 0.0
        edges_used += 1
        in_deg[tu] += 1
        out_deg[su] += 1
        merged_out[su][tu] += wt
        undirected_pairs.append((su, tu))
        adj_undir[su].add(tu)
        adj_undir[tu].add(su)

    merged_plain = {u: dict(merged_out[u]) for u in page_ids}
    out_sum = {u: sum(merged_plain.get(u, {}).values()) for u in page_ids}

    pr, pr_iters = _pagerank_directed_weighted(page_ids, merged_plain, out_sum)

    roots = _union_find(page_ids, undirected_pairs)
    unique_roots = set(roots.values())
    n_comp = len(unique_roots)

    betweenness: dict[int, float | None] = {p: None for p in page_ids}
    did_bt = n_pages <= cap and n_pages > 0
    if did_bt:
        if n_pages > 1:
            bt = _brandes_betweenness_undirected(page_ids, adj_undir)
            for p in page_ids:
                betweenness[p] = bt.get(p, 0.0)
        else:
            for p in page_ids:
                betweenness[p] = 0.0

    session.execute(delete(PageGraphMetric).where(PageGraphMetric.crawl_job_id == crawl_job_id))
    session.execute(delete(PageGraphCluster).where(PageGraphCluster.crawl_job_id == crawl_job_id))

    for p in page_ids:
        session.add(
            PageGraphMetric(
                crawl_job_id=crawl_job_id,
                page_id=p,
                pagerank=float(pr.get(p, 1.0 / n_pages)),
                in_degree=int(in_deg[p]),
                out_degree=int(out_deg[p]),
                betweenness=betweenness[p],
                closeness=None,
            ),
        )
        session.add(
            PageGraphCluster(
                crawl_job_id=crawl_job_id,
                page_id=p,
                cluster_id=int(roots[p]),
                cluster_label=None,
            ),
        )

    return GraphMetricsComputeResult(
        pages_count=n_pages,
        edges_used=edges_used,
        pagerank_iterations=pr_iters,
        weak_components_count=n_comp,
        betweenness_computed=did_bt,
    )
