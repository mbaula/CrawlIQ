"""SQLAlchemy models (import ``domain`` so mappers register on ``Base.metadata``)."""

from models.base import Base
from models.domain import (
    CrawlError,
    CrawlJob,
    InvertedIndex,
    Page,
    PageLink,
    SearchQuery,
    Term,
)

__all__ = [
    "Base",
    "CrawlJob",
    "Page",
    "PageLink",
    "CrawlError",
    "Term",
    "InvertedIndex",
    "SearchQuery",
]
