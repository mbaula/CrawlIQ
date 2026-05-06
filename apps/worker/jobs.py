"""RQ job functions (must be importable by the worker process)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from db.session import get_session_factory
from models.domain import CrawlJob
from services.crawl_persistence import crawl_and_persist_page

log = logging.getLogger("crawliq-worker.jobs")


def ping_job(message: str = "ping") -> str:
    """Smoke-test job: logs and returns a short payload."""
    log.info("ping_job start message=%s", message)
    result = f"pong:{message}"
    log.info("ping_job done result=%s", result)
    return result


def process_crawl_job(crawl_job_id: int) -> None:
    """
    Run the first crawl step for ``crawl_job_id``: ``queued``/``pending`` → ``running``,
    then ``crawl_and_persist_page`` for the seed URL; finalize ``completed`` or ``failed``.
    """
    factory = get_session_factory()
    session = factory()
    try:
        job = session.get(CrawlJob, crawl_job_id)
        if job is None:
            log.warning("process_crawl_job: crawl job %s not found", crawl_job_id)
            return
        if job.status not in ("queued", "pending"):
            log.info(
                "process_crawl_job: skip job %s status=%s",
                crawl_job_id,
                job.status,
            )
            return

        now = datetime.now(timezone.utc)
        job.status = "running"
        if job.started_at is None:
            job.started_at = now
        session.flush()

        try:
            result = crawl_and_persist_page(
                session,
                crawl_job_id,
                job.seed_url,
                depth=0,
            )
        except Exception as exc:
            log.exception(
                "process_crawl_job: crawl_and_persist_page raised job_id=%s",
                crawl_job_id,
            )
            session.rollback()
            job = session.get(CrawlJob, crawl_job_id)
            if job is not None:
                job.status = "failed"
                msg = str(exc).strip() or exc.__class__.__name__
                job.error_message = msg[:10000]
                job.finished_at = datetime.now(timezone.utc)
                session.commit()
            return

        job = session.get(CrawlJob, crawl_job_id)
        if job is None:
            return

        finished = datetime.now(timezone.utc)
        if result.status == "failed":
            job.status = "failed"
            job.error_message = result.error_message or result.error_type or "crawl failed"
        else:
            job.status = "completed"
        job.finished_at = finished
        session.commit()
        log.info(
            "process_crawl_job: done job_id=%s result=%s",
            crawl_job_id,
            result.status,
        )
    finally:
        session.close()
