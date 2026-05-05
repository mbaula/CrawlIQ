from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db
from models.domain import CrawlJob
from schemas.crawl_job import CrawlJobCreateRequest, CrawlJobCreateResponse
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
