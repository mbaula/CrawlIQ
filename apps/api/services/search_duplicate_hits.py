"""Mark search hits that are near-duplicates of a higher-ranked hit (same list, same job)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from models.domain import PageGraphEdge


def attach_near_duplicate_of_higher_ranked(
    session: Session,
    *,
    crawl_job_id: int,
    result_rows: list[dict[str, Any]],
) -> None:
    """
    Mutates each row in ``result_rows``:

    * ``is_duplicate_variant`` (bool): True when this page is linked by a ``near_duplicate``
      edge to any page that appears earlier in ``result_rows`` (higher rank).
    * ``canonical_page_id`` (int | None): The first such higher-ranked page id, if any.
    * ``duplicate_explanation`` (str | None): Short user-facing line when a duplicate variant.
    """
    for row in result_rows:
        row["is_duplicate_variant"] = False
        row["canonical_page_id"] = None
        row["duplicate_explanation"] = None

    if len(result_rows) < 2:
        return

    hit_ids = [int(r["page_id"]) for r in result_rows]
    hit_set = frozenset(hit_ids)

    stmt = select(PageGraphEdge.source_page_id, PageGraphEdge.target_page_id).where(
        PageGraphEdge.crawl_job_id == crawl_job_id,
        PageGraphEdge.edge_type == "near_duplicate",
        and_(
            PageGraphEdge.source_page_id.in_(hit_ids),
            PageGraphEdge.target_page_id.in_(hit_ids),
        ),
    )
    pairs: set[tuple[int, int]] = set()
    for src, tgt in session.execute(stmt):
        a, b = int(src), int(tgt)
        if a not in hit_set or b not in hit_set or a == b:
            continue
        pairs.add((a, b))
        pairs.add((b, a))

    for i in range(len(result_rows)):
        pid = int(result_rows[i]["page_id"])
        for j in range(i):
            prev = int(result_rows[j]["page_id"])
            if (pid, prev) in pairs:
                result_rows[i]["is_duplicate_variant"] = True
                result_rows[i]["canonical_page_id"] = prev
                result_rows[i]["duplicate_explanation"] = (
                    "Near-duplicate of a higher-ranked result in this list (same crawl job)."
                )
                break
