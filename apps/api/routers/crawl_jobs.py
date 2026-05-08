from typing import Annotated

import redis
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, distinct, func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from db.session import get_db
from models.domain import CrawlError, CrawlJob, Page, PageLink
from schemas.crawl_job import (
    CrawlErrorRead,
    CrawlJobBulkCreateRequest,
    CrawlJobBulkCreateResponse,
    CrawlJobBulkCreateItem,
    CrawlJobCreateRequest,
    CrawlJobCreateResponse,
    CrawlJobDetailRead,
    CrawlJobRead,
    CrawlJobRetryResponse,
    PageRead,
)
from services.queue import enqueue_process_crawl_job
from services.urlnorm import normalize_seed_url

router = APIRouter(prefix="/crawl-jobs", tags=["crawl-jobs"])


@router.post("", response_model=CrawlJobCreateResponse)
def create_crawl_job(
    body: CrawlJobCreateRequest,
    db: Session = Depends(get_db),
) -> CrawlJobCreateResponse:
    seed = str(body.seed_url)
    try:
        normalized = normalize_seed_url(seed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = CrawlJob(
        seed_url=seed,
        normalized_seed_url=normalized,
        status="queued",
        max_pages=body.max_pages,
        max_depth=body.max_depth,
        same_domain_only=body.same_domain_only,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    enqueued = True
    try:
        enqueue_process_crawl_job(job.id)
    except (OSError, redis.exceptions.RedisError):
        enqueued = False
    return CrawlJobCreateResponse.model_validate(job).model_copy(update={"enqueued": enqueued})


@router.post("/bulk", response_model=CrawlJobBulkCreateResponse)
def bulk_create_crawl_jobs(
    body: CrawlJobBulkCreateRequest,
    db: Session = Depends(get_db),
) -> CrawlJobBulkCreateResponse:
    results: list[CrawlJobBulkCreateItem] = []

    for seed_url in body.seed_urls:
        seed = str(seed_url).strip()
        try:
            normalized = normalize_seed_url(seed)
        except ValueError as exc:
            results.append(CrawlJobBulkCreateItem(seed_url=seed, ok=False, error=str(exc)))
            continue

        job = CrawlJob(
            seed_url=seed,
            normalized_seed_url=normalized,
            status="queued",
            max_pages=body.max_pages,
            max_depth=body.max_depth,
            same_domain_only=body.same_domain_only,
        )

        try:
            db.add(job)
            db.commit()
            db.refresh(job)
        except (SQLAlchemyError, OSError) as exc:
            results.append(CrawlJobBulkCreateItem(seed_url=seed, ok=False, error=str(exc)))
            continue

        enqueued = True
        try:
            enqueue_process_crawl_job(job.id)
        except (OSError, redis.exceptions.RedisError):
            enqueued = False

        results.append(
            CrawlJobBulkCreateItem(
                seed_url=seed,
                ok=True,
                job=CrawlJobCreateResponse.model_validate(job).model_copy(update={"enqueued": enqueued}),
            )
        )

    return CrawlJobBulkCreateResponse(results=results)


@router.get("", response_model=list[CrawlJobRead])
def list_crawl_jobs(
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CrawlJobRead]:
    stmt = (
        select(CrawlJob)
        .order_by(CrawlJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


@router.get("/{job_id}", response_model=CrawlJobDetailRead)
def get_crawl_job(job_id: int, db: Session = Depends(get_db)) -> CrawlJobDetailRead:
    job = db.get(CrawlJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="crawl job not found")
    discovered = db.scalar(
        select(func.count(distinct(PageLink.target_normalized_url))).where(
            PageLink.crawl_job_id == job_id,
            PageLink.is_crawl_eligible.is_(True),
        ),
    )
    pages_discovered = int(discovered or 0)
    denom = float(job.max_pages) if job.max_pages > 0 else 1.0
    crawl_progress = min(1.0, float(job.pages_crawled) / denom)
    payload = CrawlJobRead.model_validate(job).model_dump()
    payload["pages_discovered"] = pages_discovered
    payload["crawl_progress"] = crawl_progress
    return CrawlJobDetailRead(**payload)


@router.get("/{job_id}/pages", response_model=list[PageRead])
def list_crawl_job_pages(
    job_id: int,
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PageRead]:
    if db.get(CrawlJob, job_id) is None:
        raise HTTPException(status_code=404, detail="crawl job not found")
    stmt = (
        select(Page)
        .where(Page.crawl_job_id == job_id)
        .order_by(Page.depth.asc(), Page.id.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


@router.get("/{job_id}/errors", response_model=list[CrawlErrorRead])
def list_crawl_job_errors(
    job_id: int,
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CrawlErrorRead]:
    if db.get(CrawlJob, job_id) is None:
        raise HTTPException(status_code=404, detail="crawl job not found")
    stmt = (
        select(CrawlError)
        .where(CrawlError.crawl_job_id == job_id)
        .order_by(CrawlError.created_at.asc(), CrawlError.id.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


@router.post("/{job_id}/cancel", response_model=CrawlJobDetailRead)
def cancel_crawl_job(job_id: int, db: Session = Depends(get_db)) -> CrawlJobDetailRead:
    job = db.get(CrawlJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="crawl job not found")
    if job.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"cannot cancel job in status '{job.status}'")

    job.status = "cancelled"
    job.finished_at = func.now()
    try:
        db.commit()
        db.refresh(job)
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Reuse the existing detail response computation.
    discovered = db.scalar(
        select(func.count(distinct(PageLink.target_normalized_url))).where(
            PageLink.crawl_job_id == job_id,
            PageLink.is_crawl_eligible.is_(True),
        ),
    )
    pages_discovered = int(discovered or 0)
    denom = float(job.max_pages) if job.max_pages > 0 else 1.0
    crawl_progress = min(1.0, float(job.pages_crawled) / denom)
    payload = CrawlJobRead.model_validate(job).model_dump()
    payload["pages_discovered"] = pages_discovered
    payload["crawl_progress"] = crawl_progress
    return CrawlJobDetailRead(**payload)


@router.post("/{job_id}/retry", response_model=CrawlJobRetryResponse)
def retry_crawl_job(job_id: int, db: Session = Depends(get_db)) -> CrawlJobRetryResponse:
    job = db.get(CrawlJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="crawl job not found")
    if job.status != "failed":
        raise HTTPException(status_code=409, detail=f"cannot retry job in status '{job.status}'")

    # Reset the job and clear prior crawl artifacts so the frontier can run again.
    try:
        db.execute(delete(PageLink).where(PageLink.crawl_job_id == job_id))
        db.execute(delete(CrawlError).where(CrawlError.crawl_job_id == job_id))
        db.execute(delete(Page).where(Page.crawl_job_id == job_id))

        job.pages_crawled = 0
        job.pages_indexed = 0
        job.pages_failed = 0
        job.error_message = None
        job.started_at = None
        job.finished_at = None
        job.status = "queued"

        db.commit()
        db.refresh(job)
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    enqueued = True
    try:
        enqueue_process_crawl_job(job.id)
    except (OSError, redis.exceptions.RedisError):
        enqueued = False

    return CrawlJobRetryResponse.model_validate(job).model_copy(update={"enqueued": enqueued})
