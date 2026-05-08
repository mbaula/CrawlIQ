"""RQ job functions (must be importable by the worker process)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from db.session import get_session_factory
from models.domain import CrawlJob
from services.crawl_persistence import run_crawl_frontier

log = logging.getLogger("crawliq-worker.jobs")


def _set_current_job(job_id: int | None) -> None:
    """Register the current job ID for graceful shutdown handling."""
    try:
        from main import set_current_crawl_job

        set_current_crawl_job(job_id)
    except ImportError:
        pass  # Running in test context without main module


def ping_job(message: str = "ping") -> str:
    """Smoke-test job: logs and returns a short payload."""
    log.info("ping_job start message=%s", message)
    result = f"pong:{message}"
    log.info("ping_job done result=%s", result)
    return result


def process_crawl_job(crawl_job_id: int) -> None:
    """
    ``queued``/``pending`` → ``running``, then BFS frontier crawl (seed + eligible links)
    until limits or empty frontier; finalize ``completed`` or ``failed``.
    """
    _set_current_job(crawl_job_id)
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
        session.commit()  # Commit immediately so status is visible

        try:
            summary = run_crawl_frontier(session, crawl_job_id)
        except Exception as exc:
            log.exception(
                "process_crawl_job: run_crawl_frontier raised job_id=%s",
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
        if job.status == "cancelled":
            if job.finished_at is None:
                job.finished_at = finished
            session.commit()
            log.info("process_crawl_job: cancelled job_id=%s", crawl_job_id)
            return
        if summary.status == "failed":
            job.status = "failed"
            job.error_message = summary.error_message or "crawl failed"
        else:
            job.status = "completed"
        job.finished_at = finished
        session.commit()
        log.info(
            "process_crawl_job: done job_id=%s summary=%s",
            crawl_job_id,
            summary.status,
        )
    finally:
        _set_current_job(None)  # Clear current job on completion
        session.close()
