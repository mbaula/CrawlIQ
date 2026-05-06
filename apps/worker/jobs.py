"""RQ job functions (must be importable by the worker process)."""

from __future__ import annotations

import logging

log = logging.getLogger("crawliq-worker.jobs")


def ping_job(message: str = "ping") -> str:
    """Smoke-test job: logs and returns a short payload."""
    log.info("ping_job start message=%s", message)
    result = f"pong:{message}"
    log.info("ping_job done result=%s", result)
    return result
