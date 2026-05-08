"""Fetch outcomes for ``services.fetch_html``.

Despite the legacy filename, this fetcher can return HTML or other text-like
document bodies (e.g. Markdown) depending on content-type policy.
"""

from typing import Literal

from pydantic import BaseModel, Field


class FetchHtmlSuccess(BaseModel):
    """Successful fetch for an indexable text-like document."""

    url: str = Field(description="Requested URL")
    final_url: str = Field(description="URL after redirects")
    status_code: int
    content_type: str
    body: str = Field(description="Decoded response body (text-like)")
    elapsed_ms: int


class FetchHtmlFailure(BaseModel):
    """Fetch skipped or failed (timeouts, non-HTML, HTTP errors, limits)."""

    url: str
    final_url: str | None = Field(default=None, description="Final URL after redirects (if known)")
    kind: Literal[
        "timeout",
        "connect",
        "tls",
        "protocol",
        "redirect_error",
        "http_error",
        "not_indexable",
        "oversized",
        "invalid_url",
    ]
    reason: str
    elapsed_ms: int | None = None
    status_code: int | None = None
    content_type: str | None = None
    retry_count: int = Field(0, ge=0, description="Number of internal retries attempted before final failure.")


FetchHtmlOutcome = FetchHtmlSuccess | FetchHtmlFailure
