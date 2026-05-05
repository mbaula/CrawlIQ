"""Fetch outcomes for ``services.fetch_html``."""

from typing import Literal

from pydantic import BaseModel, Field


class FetchHtmlSuccess(BaseModel):
    """Successful HTML response."""

    url: str = Field(description="Requested URL")
    final_url: str = Field(description="URL after redirects")
    status_code: int
    content_type: str
    html: str
    elapsed_ms: int


class FetchHtmlFailure(BaseModel):
    """Fetch skipped or failed (timeouts, non-HTML, HTTP errors, limits)."""

    url: str
    kind: Literal[
        "timeout",
        "connect",
        "tls",
        "protocol",
        "redirect_error",
        "http_error",
        "not_html",
        "oversized",
        "invalid_url",
    ]
    reason: str
    elapsed_ms: int | None = None
    status_code: int | None = None
    content_type: str | None = None


FetchHtmlOutcome = FetchHtmlSuccess | FetchHtmlFailure
