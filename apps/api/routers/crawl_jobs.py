from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.session import get_db
from models.domain import CrawlError, CrawlJob, Page
from schemas.crawl_job import (
    CrawlErrorRead,
    CrawlJobCreateRequest,
    CrawlJobCreateResponse,
    CrawlJobRead,
    PageRead,
)
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
    return CrawlJobCreateResponse.model_validate(job)


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


@router.get("/{job_id}", response_model=CrawlJobRead)
def get_crawl_job(job_id: int, db: Session = Depends(get_db)) -> CrawlJobRead:
    job = db.get(CrawlJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="crawl job not found")
    return job


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
