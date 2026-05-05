"""HTTP HTML fetch: sync ``httpx``, timeouts, redirects cap, strict ``text/html``."""

from __future__ import annotations

import time

import httpx

from config import Settings, get_settings
from schemas.fetch_html import FetchHtmlFailure, FetchHtmlSuccess

DEFAULT_HTTP_USER_AGENT = "CrawlIQ/0.1"


def _effective_user_agent(settings: Settings) -> str:
    ua = (settings.crawl_http_user_agent or "").strip()
    return ua if ua else DEFAULT_HTTP_USER_AGENT


def _mime_without_params(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return content_type.split(";")[0].strip().lower() or None


def _is_html_content_type(content_type: str | None) -> bool:
    return _mime_without_params(content_type) == "text/html"


def fetch_html(
    url: str,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> FetchHtmlSuccess | FetchHtmlFailure:
    """
    GET ``url`` and return decoded HTML or a structured failure.

    * Sync ``httpx.Client``: redirect following enabled with a max redirect count.
    * Timeout from ``crawl_request_timeout_seconds``.
    * ``User-Agent`` from ``crawl_http_user_agent`` or built-in default.
    * Only **200** responses with ``Content-Type`` MIME ``text/html`` yield success.
    * Response body size capped by ``crawl_max_response_bytes``.
    """
    raw = url.strip()
    if not raw:
        return FetchHtmlFailure(
            url=url,
            kind="invalid_url",
            reason="URL is empty",
        )

    s = settings or get_settings()
    timeout = float(s.crawl_request_timeout_seconds)
    ua = _effective_user_agent(s)
    max_redirects = max(1, s.crawl_max_redirects)
    max_bytes = s.crawl_max_response_bytes

    headers = {"User-Agent": ua, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}

    def _execute(c: httpx.Client) -> FetchHtmlSuccess | FetchHtmlFailure:
        start = time.perf_counter()

        try:
            response = c.get(raw, headers=headers)
        except httpx.TimeoutException as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return FetchHtmlFailure(
                url=raw,
                kind="timeout",
                reason=str(exc) or "request timed out",
                elapsed_ms=elapsed_ms,
            )
        except httpx.TooManyRedirects as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return FetchHtmlFailure(
                url=raw,
                kind="redirect_error",
                reason=str(exc) or "too many redirects",
                elapsed_ms=elapsed_ms,
            )
        except httpx.ConnectError as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return FetchHtmlFailure(
                url=raw,
                kind="connect",
                reason=str(exc) or "connection failed",
                elapsed_ms=elapsed_ms,
            )
        except httpx.LocalProtocolError as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return FetchHtmlFailure(
                url=raw,
                kind="protocol",
                reason=str(exc) or "protocol error",
                elapsed_ms=elapsed_ms,
            )
        except httpx.RequestError as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            msg = str(exc) or "request failed"
            kind = "tls" if "certificate" in msg.lower() or "ssl" in msg.lower() else "connect"
            return FetchHtmlFailure(url=raw, kind=kind, reason=msg, elapsed_ms=elapsed_ms)

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        final_url = str(response.url)
        ct_header = response.headers.get("content-type")

        if len(response.content) > max_bytes:
            return FetchHtmlFailure(
                url=raw,
                kind="oversized",
                reason=f"response body exceeds {max_bytes} bytes",
                elapsed_ms=elapsed_ms,
                status_code=response.status_code,
                content_type=ct_header,
            )

        if response.status_code >= 400:
            return FetchHtmlFailure(
                url=raw,
                kind="http_error",
                reason=f"HTTP {response.status_code}",
                elapsed_ms=elapsed_ms,
                status_code=response.status_code,
                content_type=ct_header,
            )

        if response.status_code != 200:
            return FetchHtmlFailure(
                url=raw,
                kind="http_error",
                reason=f"unexpected status {response.status_code}",
                elapsed_ms=elapsed_ms,
                status_code=response.status_code,
                content_type=ct_header,
            )

        if not _is_html_content_type(ct_header):
            return FetchHtmlFailure(
                url=raw,
                kind="not_html",
                reason="Content-Type is not text/html",
                elapsed_ms=elapsed_ms,
                status_code=response.status_code,
                content_type=ct_header,
            )

        html = response.text
        canonical_ct = _mime_without_params(ct_header) or "text/html"

        return FetchHtmlSuccess(
            url=raw,
            final_url=final_url,
            status_code=response.status_code,
            content_type=canonical_ct,
            html=html,
            elapsed_ms=elapsed_ms,
        )

    timeout_cfg = httpx.Timeout(timeout)

    if client is not None:
        return _execute(client)

    with httpx.Client(
        timeout=timeout_cfg,
        follow_redirects=True,
        max_redirects=max_redirects,
        verify=True,
    ) as c:
        return _execute(c)
