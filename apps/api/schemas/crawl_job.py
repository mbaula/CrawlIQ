from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CrawlJobCreateRequest(BaseModel):
    seed_url: HttpUrl
    max_pages: int = Field(ge=1, le=10_000)
    max_depth: int = Field(ge=0, le=10)
    same_domain_only: bool = True


class CrawlJobCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seed_url: str
    status: str
    max_pages: int
    max_depth: int
    same_domain_only: bool
    created_at: datetime
