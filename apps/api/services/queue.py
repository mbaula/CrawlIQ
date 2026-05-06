"""Redis RQ: enqueue background jobs (worker must import the same job callables)."""

from __future__ import annotations

import redis
import redis.exceptions
from rq import Queue

from config import get_settings

_PING_JOB = "jobs.ping_job"


def _redis_url() -> str:
    s = (get_settings().redis_url or "").strip()
    return s if s else "redis://127.0.0.1:6379/0"


def get_redis_connection() -> redis.Redis:
    return redis.from_url(_redis_url())


def get_default_queue() -> Queue:
    return Queue("default", connection=get_redis_connection())


def enqueue_ping_job(message: str = "ping") -> str:
    """
    Enqueue the worker's ``jobs.ping_job`` (string path so the API image
    does not need a copy of ``jobs.py``).
    """
    q = get_default_queue()
    job = q.enqueue(_PING_JOB, message)
    return job.get_id()
