"""Minimal worker process: verifies Redis and stays up for local Compose."""

import logging
import os
import signal
import sys
import time

import redis

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("crawliq-worker")

_stop = False


def _handle_sig(_signum, _frame) -> None:
    global _stop
    _stop = True


def main() -> None:
    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    log.info(
        "CrawlIQ worker starting (max_pages=%s max_depth=%s)",
        os.environ.get("CRAWL_DEFAULT_MAX_PAGES", "?"),
        os.environ.get("CRAWL_DEFAULT_MAX_DEPTH", "?"),
    )

    r = redis.from_url(url)
    r.ping()
    log.info("Redis OK at %s", url.split("@")[-1] if "@" in url else url)

    while not _stop:
        time.sleep(30)
        r.ping()
        log.info("heartbeat: idle (crawl queue not wired yet)")


if __name__ == "__main__":
    try:
        main()
    except redis.RedisError as e:
        log.error("Redis error: %s", e)
        sys.exit(1)
