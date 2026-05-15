"""Populate ``page_graph_edges`` with ``edge_type = url_hierarchy`` from URL paths."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from yarl import URL

from crawliq_core.url_normalize import normalize_url
from models.domain import Page, PageGraphEdge

_URL_HIERARCHY_WEIGHT = 0.9
_INSERT_BATCH = 500


def _canonical_path(path: str) -> str:
    """Match ``crawliq_core.url_normalize._canonical_path`` (paths stored on pages)."""
    if not path or path == "/":
        return "/"
    stripped = path.rstrip("/")
    return stripped if stripped else "/"


def _immediate_parent_normalized_url(child_normalized: str) -> str | None:
    """
    Parent URL = same scheme/host/port as child, path = child path with last
    non-empty segment removed, then ``normalize_url`` so lookup matches ``pages``.
    """
    try:
        child = URL(child_normalized.strip())
    except ValueError:
        return None
    if not child.scheme or not child.host:
        return None
    if child.scheme not in ("http", "https"):
        return None

    path = _canonical_path(child.path)
    segments = [p for p in path.split("/") if p]
    if not segments:
        return None

    parent_segments = segments[:-1]
    parent_path = "/" if not parent_segments else "/" + "/".join(parent_segments)

    built = str(
        URL.build(
            scheme=child.scheme,
            host=child.host,
            port=child.port,
            path=parent_path,
        ),
    )
    try:
        return normalize_url(built)
    except ValueError:
        return None


def _hierarchy_evidence_dict(parent_normalized: str, child_normalized: str) -> dict[str, str]:
    pu, cu = URL(parent_normalized), URL(child_normalized)
    return {
        "child_path": _canonical_path(cu.path),
        "parent_path": _canonical_path(pu.path),
    }


def _hierarchy_evidence_json(parent_normalized: str, child_normalized: str) -> str:
    return json.dumps(
        _hierarchy_evidence_dict(parent_normalized, child_normalized),
        sort_keys=True,
    )


def generate_url_hierarchy_edges_for_job(session: Session, crawl_job_id: int) -> int:
    """
    Insert ``url_hierarchy`` edges (parent page → child page) when the child's
    immediate URL parent exists in the same job. Idempotent via ``ON CONFLICT DO NOTHING``.

    Returns the number of rows inserted this run (excludes conflicts).
    """
    rows = session.execute(
        select(Page.id, Page.normalized_url).where(Page.crawl_job_id == crawl_job_id),
    ).all()
    url_to_id: dict[str, int] = {normalized_url: page_id for page_id, normalized_url in rows}

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

    for child_id, child_url in rows:
        parent_url = _immediate_parent_normalized_url(child_url)
        if parent_url is None or parent_url == child_url:
            continue
        parent_id = url_to_id.get(parent_url)
        if parent_id is None or parent_id == child_id:
            continue
        batch.append(
            {
                "crawl_job_id": crawl_job_id,
                "source_page_id": parent_id,
                "target_page_id": child_id,
                "edge_type": "url_hierarchy",
                "weight": _URL_HIERARCHY_WEIGHT,
                "evidence": _hierarchy_evidence_dict(parent_url, child_url),
            },
        )
        if len(batch) >= _INSERT_BATCH:
            flush()

    flush()
    return inserted_total
