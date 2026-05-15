"""Backfill ``page_graph_edges`` (+ metrics) for every crawl job.

Run inside the API container (same DB config as the app), for example::

    docker compose run --rm \\
      -e DATABASE_URL=postgresql://crawliq:crawliq_dev@postgres:5432/crawliq \\
      api python backfill_all_job_graph_edges.py

Or from a shell already in ``/app`` with ``DATABASE_URL`` set.
"""

from __future__ import annotations

import sys
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from config import get_settings
from db.session import get_session_factory
from models.domain import CrawlJob
from services.page_graph_content_similarity import generate_content_similarity_edges_for_job
from services.page_graph_link_edges import generate_link_edges_for_job
from services.page_graph_metrics import compute_graph_metrics_for_job
from services.page_graph_near_duplicate import generate_near_duplicate_edges_for_job
from services.page_graph_url_hierarchy_edges import generate_url_hierarchy_edges_for_job


def _die(msg: str, code: int = 1) -> NoReturn:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def main() -> None:
    settings = get_settings()
    if not (settings.database_url or "").strip():
        _die("DATABASE_URL is not set.")

    sf = get_session_factory()
    with sf() as s:
        job_ids = list(s.scalars(select(CrawlJob.id).order_by(CrawlJob.id.asc())).all())

    if not job_ids:
        print("No crawl jobs found; nothing to do.")
        return

    print(f"Backfilling graph data for {len(job_ids)} job(s): {job_ids}")

    for jid in job_ids:
        print(f"\n--- job {jid} ---")
        with sf() as session:
            try:
                n_link = generate_link_edges_for_job(session, jid)
                session.commit()
                print(f"  link_edges:           {n_link} inserted")

                n_url = generate_url_hierarchy_edges_for_job(session, jid)
                session.commit()
                print(f"  url_hierarchy_edges:  {n_url} inserted")

                n_sim = generate_content_similarity_edges_for_job(session, jid, settings=settings)
                session.commit()
                print(f"  content_similarity:   {n_sim} inserted")

                n_nd = generate_near_duplicate_edges_for_job(session, jid, settings=settings)
                session.commit()
                print(f"  near_duplicate:       {n_nd} inserted")

                metrics = compute_graph_metrics_for_job(session, jid, settings=settings)
                session.commit()
                print(
                    "  metrics:              "
                    f"pages={metrics.pages_count} edges_used={metrics.edges_used} "
                    f"pr_iters={metrics.pagerank_iterations} components={metrics.weak_components_count} "
                    f"betweenness={metrics.betweenness_computed}",
                )
            except (SQLAlchemyError, OSError, ValueError) as exc:
                session.rollback()
                print(f"  ERROR: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
