"""Integration tests for read-only graph APIs."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.session import get_db
from db.url import sync_engine_url
from main import app
from models.domain import (
    CrawlJob,
    Page,
    PageGraphCluster,
    PageGraphEdge,
    PageGraphMetric,
)


def test_subgraph_missing_job_id_returns_422_no_database() -> None:
    mock_session = MagicMock()

    def _get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _get_db
    try:
        with TestClient(app) as client:
            r = client.get("/graph/subgraph", params={"page_id": 1})
            assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def graph_api_client(test_database_url: str):
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()

    def _get_db():
        yield session

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as client:
        yield client, session
    session.close()
    app.dependency_overrides.clear()


@pytest.mark.integration
def test_subgraph_job_not_found(graph_api_client) -> None:
    client, _session = graph_api_client
    r = client.get("/graph/subgraph", params={"job_id": 9_999_999, "page_id": 1})
    assert r.status_code == 404
    assert r.json()["detail"] == "crawl job not found"


@pytest.mark.integration
def test_subgraph_page_not_found_and_wrong_job(graph_api_client) -> None:
    client, session = graph_api_client
    job = CrawlJob(
        seed_url="https://g.example/",
        normalized_seed_url="https://g.example/",
        status="completed",
    )
    session.add(job)
    session.flush()
    p = Page(
        crawl_job_id=job.id,
        url="https://g.example/a",
        normalized_url="https://g.example/a",
        domain="g.example",
        depth=0,
    )
    session.add(p)
    session.commit()

    r = client.get("/graph/subgraph", params={"job_id": job.id, "page_id": 9_999_999})
    assert r.status_code == 404
    assert r.json()["detail"] == "page not found"

    job2 = CrawlJob(
        seed_url="https://other.example/",
        normalized_seed_url="https://other.example/",
        status="completed",
    )
    session.add(job2)
    session.commit()

    r2 = client.get("/graph/subgraph", params={"job_id": job2.id, "page_id": p.id})
    assert r2.status_code == 404
    assert r2.json()["detail"] == "page not found"


@pytest.mark.integration
def test_subgraph_isolated_center_empty_edges(graph_api_client) -> None:
    client, session = graph_api_client
    job = CrawlJob(
        seed_url="https://iso.example/",
        normalized_seed_url="https://iso.example/",
        status="completed",
    )
    session.add(job)
    session.flush()
    p = Page(
        crawl_job_id=job.id,
        url="https://iso.example/only",
        normalized_url="https://iso.example/only",
        domain="iso.example",
        title="Lonely",
        depth=0,
    )
    session.add(p)
    session.commit()

    r = client.get(
        "/graph/subgraph",
        params={"job_id": job.id, "page_id": p.id, "radius": 3, "max_nodes": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["nodes"] == [
        {
            "page_id": p.id,
            "title": "Lonely",
            "url": "https://iso.example/only",
            "normalized_url": "https://iso.example/only",
            "depth": 0,
            "metrics": None,
            "cluster_id": None,
        }
    ]
    assert body["edges"] == []


@pytest.mark.integration
def test_subgraph_radius_zero_only_center(graph_api_client) -> None:
    client, session = graph_api_client
    job = CrawlJob(
        seed_url="https://r0.example/",
        normalized_seed_url="https://r0.example/",
        status="completed",
    )
    session.add(job)
    session.flush()
    p1 = Page(
        crawl_job_id=job.id,
        url="https://r0.example/a",
        normalized_url="https://r0.example/a",
        domain="r0.example",
        depth=0,
    )
    p2 = Page(
        crawl_job_id=job.id,
        url="https://r0.example/b",
        normalized_url="https://r0.example/b",
        domain="r0.example",
        depth=1,
    )
    session.add_all([p1, p2])
    session.flush()
    session.add(
        PageGraphEdge(
            crawl_job_id=job.id,
            source_page_id=p1.id,
            target_page_id=p2.id,
            edge_type="link",
            weight=1.0,
        ),
    )
    session.commit()

    r = client.get(
        "/graph/subgraph",
        params={"job_id": job.id, "page_id": p1.id, "radius": 0, "max_nodes": 50},
    )
    assert r.status_code == 200
    assert len(r.json()["nodes"]) == 1
    assert r.json()["nodes"][0]["page_id"] == p1.id
    assert r.json()["edges"] == []


@pytest.mark.integration
def test_subgraph_max_nodes_limits_bfs(graph_api_client) -> None:
    client, session = graph_api_client
    job = CrawlJob(
        seed_url="https://cap.example/",
        normalized_seed_url="https://cap.example/",
        status="completed",
    )
    session.add(job)
    session.flush()
    pages = [
        Page(
            crawl_job_id=job.id,
            url=f"https://cap.example/{i}",
            normalized_url=f"https://cap.example/{i}",
            domain="cap.example",
            depth=i,
        )
        for i in range(3)
    ]
    session.add_all(pages)
    session.flush()
    a, b, c = pages
    session.add_all(
        [
            PageGraphEdge(
                crawl_job_id=job.id,
                source_page_id=a.id,
                target_page_id=b.id,
                edge_type="link",
                weight=1.0,
            ),
            PageGraphEdge(
                crawl_job_id=job.id,
                source_page_id=b.id,
                target_page_id=c.id,
                edge_type="link",
                weight=1.0,
            ),
        ],
    )
    session.commit()

    r = client.get(
        "/graph/subgraph",
        params={"job_id": job.id, "page_id": a.id, "radius": 5, "max_nodes": 2},
    )
    assert r.status_code == 200
    ids = [n["page_id"] for n in r.json()["nodes"]]
    assert ids == sorted(ids)
    assert len(ids) == 2
    assert a.id in ids and b.id in ids

    r2 = client.get(
        "/graph/subgraph",
        params={"job_id": job.id, "page_id": a.id, "radius": 5, "max_nodes": 3},
    )
    assert len(r2.json()["nodes"]) == 3


@pytest.mark.integration
def test_subgraph_stable_ordering_and_edge_sort(graph_api_client) -> None:
    client, session = graph_api_client
    job = CrawlJob(
        seed_url="https://sort.example/",
        normalized_seed_url="https://sort.example/",
        status="completed",
    )
    session.add(job)
    session.flush()
    p1 = Page(
        crawl_job_id=job.id,
        url="https://sort.example/1",
        normalized_url="https://sort.example/1",
        domain="sort.example",
        depth=0,
    )
    p2 = Page(
        crawl_job_id=job.id,
        url="https://sort.example/2",
        normalized_url="https://sort.example/2",
        domain="sort.example",
        depth=1,
    )
    session.add_all([p1, p2])
    session.flush()
    session.add_all(
        [
            PageGraphEdge(
                crawl_job_id=job.id,
                source_page_id=p2.id,
                target_page_id=p1.id,
                edge_type="url_hierarchy",
                weight=0.5,
                evidence={"k": "v"},
            ),
            PageGraphEdge(
                crawl_job_id=job.id,
                source_page_id=p1.id,
                target_page_id=p2.id,
                edge_type="link",
                weight=1.0,
            ),
        ],
    )
    session.commit()

    params = {"job_id": job.id, "page_id": p1.id, "radius": 1, "max_nodes": 50}
    b1 = client.get("/graph/subgraph", params=params).json()
    b2 = client.get("/graph/subgraph", params=params).json()
    assert b1 == b2
    assert [n["page_id"] for n in b1["nodes"]] == sorted([p1.id, p2.id])
    et_order = [e["edge_type"] for e in b1["edges"]]
    assert et_order == ["link", "url_hierarchy"]


@pytest.mark.integration
def test_neighbors_matches_radius_one_subgraph(graph_api_client) -> None:
    client, session = graph_api_client
    job = CrawlJob(
        seed_url="https://nbr.example/",
        normalized_seed_url="https://nbr.example/",
        status="completed",
    )
    session.add(job)
    session.flush()
    p1 = Page(
        crawl_job_id=job.id,
        url="https://nbr.example/a",
        normalized_url="https://nbr.example/a",
        domain="nbr.example",
        depth=0,
    )
    p2 = Page(
        crawl_job_id=job.id,
        url="https://nbr.example/b",
        normalized_url="https://nbr.example/b",
        domain="nbr.example",
        depth=1,
    )
    session.add_all([p1, p2])
    session.flush()
    session.add(
        PageGraphEdge(
            crawl_job_id=job.id,
            source_page_id=p1.id,
            target_page_id=p2.id,
            edge_type="link",
            weight=1.0,
        ),
    )
    session.commit()

    sub = client.get(
        "/graph/subgraph",
        params={"job_id": job.id, "page_id": p1.id, "radius": 1, "max_nodes": 50},
    ).json()
    nbr = client.get(
        f"/pages/{p1.id}/neighbors",
        params={"job_id": job.id, "max_nodes": 50},
    ).json()
    assert sub["nodes"] == nbr["nodes"]
    assert sub["edges"] == nbr["edges"]


@pytest.mark.integration
def test_page_graph_matches_subgraph_same_params(graph_api_client) -> None:
    client, session = graph_api_client
    job = CrawlJob(
        seed_url="https://pg.example/",
        normalized_seed_url="https://pg.example/",
        status="completed",
    )
    session.add(job)
    session.flush()
    p1 = Page(
        crawl_job_id=job.id,
        url="https://pg.example/a",
        normalized_url="https://pg.example/a",
        domain="pg.example",
        depth=0,
    )
    session.add(p1)
    session.commit()

    sub = client.get(
        "/graph/subgraph",
        params={"job_id": job.id, "page_id": p1.id, "radius": 2, "max_nodes": 40},
    ).json()
    pg = client.get(
        f"/pages/{p1.id}/graph",
        params={"job_id": job.id, "radius": 2, "max_nodes": 40},
    ).json()
    assert sub == pg


@pytest.mark.integration
def test_subgraph_includes_metrics_and_cluster(graph_api_client) -> None:
    client, session = graph_api_client
    job = CrawlJob(
        seed_url="https://mc.example/",
        normalized_seed_url="https://mc.example/",
        status="completed",
    )
    session.add(job)
    session.flush()
    p = Page(
        crawl_job_id=job.id,
        url="https://mc.example/x",
        normalized_url="https://mc.example/x",
        domain="mc.example",
        depth=0,
    )
    session.add(p)
    session.flush()
    session.add(
        PageGraphMetric(
            crawl_job_id=job.id,
            page_id=p.id,
            pagerank=0.25,
            in_degree=1,
            out_degree=2,
            betweenness=None,
            closeness=None,
        ),
    )
    session.add(
        PageGraphCluster(
            crawl_job_id=job.id,
            page_id=p.id,
            cluster_id=p.id,
            cluster_label="root",
        ),
    )
    session.commit()

    r = client.get(
        "/graph/subgraph",
        params={"job_id": job.id, "page_id": p.id, "radius": 0, "max_nodes": 10},
    )
    assert r.status_code == 200
    node = r.json()["nodes"][0]
    assert node["cluster_id"] == p.id
    assert node["metrics"] == {
        "pagerank": 0.25,
        "in_degree": 1,
        "out_degree": 2,
        "betweenness": None,
        "closeness": None,
    }


@pytest.mark.integration
def test_graph_stats(graph_api_client) -> None:
    client, session = graph_api_client
    job = CrawlJob(
        seed_url="https://st.example/",
        normalized_seed_url="https://st.example/",
        status="completed",
    )
    session.add(job)
    session.flush()
    p1 = Page(
        crawl_job_id=job.id,
        url="https://st.example/1",
        normalized_url="https://st.example/1",
        domain="st.example",
        depth=0,
    )
    p2 = Page(
        crawl_job_id=job.id,
        url="https://st.example/2",
        normalized_url="https://st.example/2",
        domain="st.example",
        depth=1,
    )
    session.add_all([p1, p2])
    session.flush()
    session.add_all(
        [
            PageGraphEdge(
                crawl_job_id=job.id,
                source_page_id=p1.id,
                target_page_id=p2.id,
                edge_type="link",
                weight=1.0,
            ),
            PageGraphEdge(
                crawl_job_id=job.id,
                source_page_id=p2.id,
                target_page_id=p1.id,
                edge_type="url_hierarchy",
                weight=1.0,
            ),
        ],
    )
    session.add(PageGraphMetric(crawl_job_id=job.id, page_id=p1.id, pagerank=0.5, in_degree=0, out_degree=1))
    session.add(PageGraphCluster(crawl_job_id=job.id, page_id=p1.id, cluster_id=1))
    session.add(PageGraphCluster(crawl_job_id=job.id, page_id=p2.id, cluster_id=1))
    session.commit()

    r = client.get("/graph/stats", params={"job_id": job.id})
    assert r.status_code == 200
    b = r.json()
    assert b["crawl_job_id"] == job.id
    assert b["page_count"] == 2
    assert b["edge_count"] == 2
    assert b["page_graph_metrics_count"] == 1
    assert b["page_graph_cluster_rows"] == 2
    assert b["distinct_cluster_ids"] == 1
    by_type = {x["edge_type"]: x["count"] for x in b["edge_counts_by_type"]}
    assert by_type["link"] == 1
    assert by_type["url_hierarchy"] == 1


@pytest.mark.integration
def test_graph_clusters_pagination(graph_api_client) -> None:
    client, session = graph_api_client
    job = CrawlJob(
        seed_url="https://cl.example/",
        normalized_seed_url="https://cl.example/",
        status="completed",
    )
    session.add(job)
    session.flush()
    pages = [
        Page(
            crawl_job_id=job.id,
            url=f"https://cl.example/{i}",
            normalized_url=f"https://cl.example/{i}",
            domain="cl.example",
            depth=0,
        )
        for i in range(3)
    ]
    session.add_all(pages)
    session.flush()
    for i, p in enumerate(pages):
        session.add(
            PageGraphCluster(
                crawl_job_id=job.id,
                page_id=p.id,
                cluster_id=10 + i,
                cluster_label=f"L{i}",
            ),
        )
    session.commit()

    r = client.get("/graph/clusters", params={"job_id": job.id, "limit": 2, "offset": 0})
    assert r.status_code == 200
    b = r.json()
    assert b["total"] == 3
    assert len(b["items"]) == 2
    assert b["limit"] == 2
    assert b["offset"] == 0
    assert b["items"][0]["cluster_id"] <= b["items"][1]["cluster_id"]

    r2 = client.get("/graph/clusters", params={"job_id": job.id, "limit": 2, "offset": 2})
    assert len(r2.json()["items"]) == 1


@pytest.mark.integration
def test_graph_stats_job_not_found(graph_api_client) -> None:
    client, _ = graph_api_client
    r = client.get("/graph/stats", params={"job_id": 8_888_888})
    assert r.status_code == 404


@pytest.mark.integration
def test_graph_clusters_job_not_found(graph_api_client) -> None:
    client, _ = graph_api_client
    r = client.get("/graph/clusters", params={"job_id": 8_888_888})
    assert r.status_code == 404
