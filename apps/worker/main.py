"""RQ worker: consumes the ``default`` queue (Redis URL from ``REDIS_URL``).

Handles graceful shutdown and recovers orphaned jobs on startup.
"""

from __future__ import annotations

import logging
import os
import signal
from datetime import datetime, timedelta, timezone

import redis
from rq import Queue, Worker
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("crawliq-worker")

# Track the currently running crawl job ID for graceful shutdown
_current_crawl_job_id: int | None = None


def set_current_crawl_job(job_id: int | None) -> None:
    """Called by jobs.py to track which crawl job is in progress."""
    global _current_crawl_job_id
    _current_crawl_job_id = job_id


def get_current_crawl_job() -> int | None:
    """Get the currently running crawl job ID."""
    return _current_crawl_job_id


def _get_db_session():
    """Create a database session for recovery operations."""
    from db.url import sync_engine_url

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return None
    engine = create_engine(sync_engine_url(db_url), pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    return Session()


def _recover_orphaned_jobs(redis_conn: redis.Redis) -> None:
    """
    On startup, recover jobs that were orphaned by a previous worker crash:
    1. Mark 'running' jobs older than 10 minutes as 'failed' (stale)
    2. Re-enqueue 'queued' jobs that have no RQ job

    Uses a distributed lock to prevent multiple workers from racing on recovery.
    """
    # Try to acquire a distributed lock for recovery (expires after 60 seconds)
    lock_key = "crawliq:recovery_lock"
    lock_acquired = redis_conn.set(lock_key, "1", nx=True, ex=60)
    if not lock_acquired:
        log.info("Another worker is handling recovery, skipping")
        return

    session = _get_db_session()
    if session is None:
        log.warning("Cannot recover orphaned jobs: DATABASE_URL not set")
        redis_conn.delete(lock_key)
        return

    try:
        from models.domain import CrawlJob

        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)

        # Find and fail stale 'running' jobs (no heartbeat mechanism yet, use started_at)
        stale_running = session.execute(
            select(CrawlJob).where(
                CrawlJob.status == "running",
                CrawlJob.started_at < stale_threshold,
            )
        ).scalars().all()

        for job in stale_running:
            log.warning(
                "Failing stale running job %s (started_at=%s)",
                job.id,
                job.started_at,
            )
            job.status = "failed"
            job.error_message = "Worker crashed or was restarted while job was running"
            job.finished_at = datetime.now(timezone.utc)

        if stale_running:
            session.commit()
            log.info("Failed %d stale running jobs", len(stale_running))

        # Find 'queued' jobs and re-enqueue them
        queued_jobs = session.execute(
            select(CrawlJob).where(CrawlJob.status == "queued")
        ).scalars().all()

        if queued_jobs:
            from rq import Queue

            queue = Queue("default", connection=redis_conn)
            timeout_seconds = int(os.environ.get("CRAWL_JOB_TIMEOUT_SECONDS", "3600"))

            for job in queued_jobs:
                log.info("Re-enqueuing orphaned queued job %s", job.id)
                queue.enqueue_call(
                    "jobs.process_crawl_job",
                    args=(job.id,),
                    timeout=timeout_seconds,
                )

            log.info("Re-enqueued %d orphaned queued jobs", len(queued_jobs))

    except Exception as exc:
        log.exception("Error recovering orphaned jobs: %s", exc)
    finally:
        session.close()
        redis_conn.delete(lock_key)


def _mark_current_job_failed(signum, frame) -> None:
    """Signal handler to mark the current job as failed on shutdown."""
    job_id = get_current_crawl_job()
    if job_id is not None:
        log.warning(
            "Received signal %s, marking job %s as failed",
            signal.Signals(signum).name,
            job_id,
        )
        session = _get_db_session()
        if session:
            try:
                from models.domain import CrawlJob

                job = session.get(CrawlJob, job_id)
                if job and job.status == "running":
                    job.status = "failed"
                    job.error_message = f"Worker shutdown (signal {signal.Signals(signum).name})"
                    job.finished_at = datetime.now(timezone.utc)
                    session.commit()
                    log.info("Marked job %s as failed due to shutdown", job_id)
            except Exception as exc:
                log.exception("Error marking job as failed: %s", exc)
            finally:
                session.close()

    # Re-raise the signal to allow normal RQ shutdown
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def main() -> None:
    raw = os.environ.get("REDIS_URL", "redis://localhost:6379/0").strip()
    redis_url = raw or "redis://localhost:6379/0"

    log.info(
        "Starting RQ worker (CRAWL_DEFAULT_MAX_PAGES=%s CRAWL_DEFAULT_MAX_DEPTH=%s)",
        os.environ.get("CRAWL_DEFAULT_MAX_PAGES", "?"),
        os.environ.get("CRAWL_DEFAULT_MAX_DEPTH", "?"),
    )

    conn = redis.from_url(redis_url)
    conn.ping()
    log.info("Redis OK at %s", redis_url.split("@")[-1] if "@" in redis_url else redis_url)

    # Recover orphaned jobs from previous crashes before starting to process new ones
    _recover_orphaned_jobs(conn)

    # Install signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _mark_current_job_failed)
    signal.signal(signal.SIGINT, _mark_current_job_failed)

    queues = [Queue("default", connection=conn)]
    worker = Worker(queues, connection=conn)
    log.info(
        "Listening on queue 'default'; jobs: jobs.ping_job, jobs.process_crawl_job",
    )
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
