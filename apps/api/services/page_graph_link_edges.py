"""Populate ``page_graph_edges`` with ``edge_type = link`` from ``page_links``."""

from __future__ import annotations

import json

from sqlalchemy import Float, Text, and_, cast, literal, select
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.orm import Session, aliased

from models.domain import Page, PageGraphEdge, PageLink

# Canonical JSON string (sorted keys) for stable ``jsonb`` storage and tests.
LINK_EDGE_EVIDENCE_JSON = json.dumps({"source": "direct_internal_link"}, sort_keys=True)


def generate_link_edges_for_job(session: Session, crawl_job_id: int) -> int:
    """
    Insert ``link`` edges where ``page_links.target_normalized_url`` resolves to a
    ``pages`` row in the same job. Ignores ``page_links.target_page_id`` and
    ``is_crawl_eligible``. Skips self-links. Idempotent via ``ON CONFLICT DO NOTHING``.

    Returns the number of rows inserted this run (excludes conflicts).
    """
    target = aliased(Page, name="link_target_page")

    inner = (
        select(
            PageLink.crawl_job_id,
            PageLink.source_page_id,
            target.id.label("target_page_id"),
            cast(literal("link"), Text).label("edge_type"),
            cast(literal(1.0), Float).label("weight"),
            cast(literal(LINK_EDGE_EVIDENCE_JSON), JSONB).label("evidence"),
        )
        .select_from(PageLink)
        .join(
            target,
            and_(
                target.crawl_job_id == PageLink.crawl_job_id,
                target.normalized_url == PageLink.target_normalized_url,
            ),
        )
        .where(PageLink.crawl_job_id == crawl_job_id)
        .where(PageLink.source_page_id != target.id)
    )

    stmt = (
        pg_insert(PageGraphEdge.__table__)
        .from_select(
            [
                "crawl_job_id",
                "source_page_id",
                "target_page_id",
                "edge_type",
                "weight",
                "evidence",
            ],
            inner,
        )
        .on_conflict_do_nothing(constraint="uq_page_graph_edges_job_src_tgt_type")
        .returning(PageGraphEdge.__table__.c.id)
    )

    result = session.execute(stmt)
    return len(result.fetchall())
