"""RQ worker: consumes the ``default`` queue (Redis URL from ``REDIS_URL``)."""

from __future__ import annotations

import logging
import os

import redis
from rq import Queue, Worker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("crawliq-worker")


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

    queues = [Queue("default", connection=conn)]
    worker = Worker(queues, connection=conn)
    log.info(
        "Listening on queue 'default'; jobs: jobs.ping_job, jobs.process_crawl_job",
    )
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
