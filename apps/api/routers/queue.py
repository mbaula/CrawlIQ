"""Dev/test endpoint to enqueue RQ jobs."""

import redis.exceptions
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.queue import enqueue_ping_job

router = APIRouter(prefix="/queue", tags=["queue"])


class QueuePingBody(BaseModel):
    message: str = Field(default="ping", min_length=1, max_length=200)


@router.post("/ping")
def post_queue_ping(body: QueuePingBody) -> dict[str, str]:
    """
    Enqueue a ``ping_job`` on the default RQ queue (worker must be running).
    Not authenticated—use only in trusted networks; remove or protect for production.
    """
    try:
        job_id = enqueue_ping_job(body.message)
    except (redis.exceptions.RedisError, OSError) as exc:
        raise HTTPException(status_code=503, detail=f"queue/redis: {exc}") from exc
    return {"queue": "default", "job_id": job_id}
